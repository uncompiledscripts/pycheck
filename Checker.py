# -*- coding: utf-8 -*-
"""
LinkedIn Premium Trial Link Checker - v4.0 (Production Release)

This application provides a comprehensive graphical user interface (GUI) to automate
the process of checking LinkedIn URLs for valid Premium trial or gift offers. This
version merges features from previous iterations with robust error handling, advanced
type safety for Pylance, and an expanded keyword detection system.
"""

import json
import logging
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# --- Dynamic & Type-Safe Imports for Selenium ---
# This block ensures the application is Pylance-compliant and functional
# even if Selenium is not installed, by providing comprehensive mock classes.

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
        WebDriverException
    )
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

    class MockOptions:
        """A mock class for Selenium options to satisfy type checkers."""
        def add_argument(self, argument: str): pass
        def add_experimental_option(self, name: str, value: Any): pass
        def set_preference(self, name: str, value: Any): pass

    class MockChromeOptions(MockOptions): pass
    class MockFirefoxOptions(MockOptions): pass

    class MockService:
        """A mock class for Selenium Service objects."""
        def __init__(self, executable_path: str = ""): pass

    class MockDriverManager:
        """A mock for WebDriver Manager."""
        def install(self) -> str: return "mock_driver_path"

    class MockWebElement:
        """A mock for Selenium WebElement."""
        def send_keys(self, value: str): pass
        def click(self): pass
        @property
        def text(self) -> str: return "mock text"
        def get_attribute(self, name: str) -> Optional[str]: return f"mock_attr_{name}"

    class MockWebDriver:
        """A comprehensive mock for the Selenium WebDriver."""
        current_url: str = "http://mock.url"
        page_source: str = "mock page source"
        title: str = "Mock Page"
        def get(self, url: str): pass
        def quit(self): pass
        def find_element(self, by: str, value: str) -> 'MockWebElement': return MockWebElement()
        def find_elements(self, by: str, value: str) -> List['MockWebElement']: return [MockWebElement()]
        def set_page_load_timeout(self, time_to_wait: int): pass
        def execute_script(self, script: str, *args: Any) -> Any: pass
        def execute_cdp_cmd(self, cmd: str, cmd_args: Dict[str, Any]) -> Any: pass

    class MockBy:
        """A mock for Selenium's By class."""
        ID = "id"; XPATH = "xpath"; TAG_NAME = "tag_name"

    class MockWebDriverWait:
        """A mock for Selenium's WebDriverWait."""
        def __init__(self, driver: Any, timeout: float): pass
        def until(self, method: Callable[[Any], Any], message: str = '') -> Any: return MockWebElement()

    class MockEC:
        """A mock for Selenium's expected_conditions."""
        @staticmethod
        def presence_of_element_located(locator: Tuple[str, str]) -> Callable[[Any], MockWebElement]:
            return lambda driver: MockWebElement()
        @staticmethod
        def url_contains(url_substring: str) -> Callable[[Any], bool]:
            return lambda driver: True
        @staticmethod
        def any_of(*expected_conditions: Callable[[Any], Any]) -> Callable[[Any], bool]:
            return lambda driver: True

    # Assign mock classes to the names used by the application
    WebDriver, WebElement, By, WebDriverWait, EC = MockWebDriver, MockWebElement, MockBy, MockWebDriverWait, MockEC
    ChromeOptions, FirefoxOptions = MockChromeOptions, MockFirefoxOptions
    ChromeService, FirefoxService = MockService, MockService
    ChromeDriverManager, GeckoDriverManager = MockDriverManager, MockDriverManager
    TimeoutException, NoSuchElementException, WebDriverException = type('TimeoutException', (Exception,), {}), type('NoSuchElementException', (Exception,), {}), type('WebDriverException', (Exception,), {})

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# --- Global Configuration & Constants ---
if getattr(sys, 'frozen', False):
    application_path = Path(sys.executable).parent
else:
    application_path = Path(__file__).parent

CONFIG_FILE = application_path / 'config.json'
LOG_DIR = application_path / 'logs'
DEFAULT_INPUT_FILE = str(application_path / "linkedin_links.txt")
DEFAULT_OUTPUT_DIR = str(application_path / "results")

RATE_LIMIT_COOLDOWN_MINUTES = 5
DEFAULT_ACCOUNT_SWITCH_THRESHOLD = 50
MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN = 5

# --- Logger Setup ---
class QueueHandler(logging.Handler):
    """A thread-safe logging handler that puts records into a queue for the GUI thread."""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record: logging.LogRecord):
        self.log_queue.put(self.format(record))

def setup_logging(log_level: int = logging.INFO, log_queue: Optional[queue.Queue] = None) -> logging.Logger:
    """Configures and returns a logger instance for file and/or GUI logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_format = '%(asctime)s|%(levelname)-8s|%(name)-15s| L:%(lineno)-4d|%(message)s'
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        file_handler = logging.FileHandler(LOG_DIR / f'linkedin_checker_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except Exception as e:
        print(f"CRITICAL: Could not set up file logger in '{LOG_DIR}'. Error: {e}")

    logger_name = "LinkedInCheckerApp"
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setFormatter(formatter)
        handlers.append(queue_handler)
        logger_name = "GUILogger"

    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    if logger.hasHandlers():
        logger.handlers.clear()
    for handler in handlers:
        handler.setLevel(log_level)
        logger.addHandler(handler)
    logger.propagate = False
    return logger

main_file_logger = setup_logging(log_level=logging.INFO)

# --- Prerequisite Checks ---
def check_prerequisites():
    """Checks if all required libraries are installed and shows an error if not."""
    missing_libs = []
    if not hasattr(sys.modules.get('customtkinter'), 'CTk'):
        missing_libs.append("customtkinter")
    if not PIL_AVAILABLE:
        main_file_logger.warning("Pillow (PIL) not found. Image-related features disabled.")
    if not SELENIUM_AVAILABLE:
        missing_libs.append("selenium and webdriver-manager")
    if missing_libs:
        error_msg = (f"Required libraries are missing:\n- {', '.join(missing_libs)}\n\n"
                     "Please install them using pip:\npip install selenium webdriver-manager customtkinter Pillow")
        try:
            root_err = tk.Tk()
            root_err.withdraw()
            messagebox.showerror("Prerequisite Error", error_msg)
            root_err.destroy()
        except tk.TclError:
            print(f"CRITICAL ERROR:\n{error_msg}")
        sys.exit(1)

# --- Data Models ---
@dataclass
class LinkResult:
    """Holds the result of checking a single LinkedIn link."""
    link: str
    status: str
    result_details: str = ""
    final_url: Optional[str] = None
    original_url_from_file: Optional[str] = None
    line_num: Optional[int] = None
    confidence: Optional[str] = None
    error: Optional[str] = None

# --- Core Checker Class ---
class EnhancedLinkedInChecker:
    """Handles the core logic of checking LinkedIn links using Selenium."""
    LOGIN_USERNAME_ID, LOGIN_PASSWORD_ID, LOGIN_SUBMIT_XPATH = "username", "password", "//button[@type='submit']"
    
    RATE_LIMIT_KEYWORDS = [
        "security verification", "are you a human", "too many requests", "temporarily restricted", 
        "checkpoint", "verify your identity", "unusual activity", "prove you're not a robot",
        "let's do a quick security check", "complete this puzzle", "captcha", "suspicious activity",
        "access to your account has been temporarily restricted", "confirm your account", 
        "help us keep your account safe", "authwall", "login_verify", "checkpoint/challenge",
        "rate limit", "blocked", "restricted access", "verify account", "security check"
    ]
    OFFER_UNAVAILABLE_KEYWORDS = [
        "offer is no longer available", "this offer has expired", "sorry, this offer isn't available", 
        "unable to claim this offer", "this link is no longer active", "link has expired", 
        "not a valid offer", "this gift is no longer available", "this trial is no longer available", 
        "you may have already redeemed this gift", "offer already redeemed", "no longer valid",
        "not available at this time", "cannot be claimed", "already been redeemed", 
        "this promotion has ended", "the page you’re looking for is not available", 
        "this offer has been fully claimed", "we could not process your request", "something went wrong",
        "looks like that gift has been claimed", "offer-expired", "gift-redeemed", "page not found"
    ]
    TRIAL_KEYWORDS = [
        "try premium for free", "start your free month", "1-month free trial", "get premium free", 
        "free trial", "claim your free month", "unlock premium free", "try for free", 
        "activate your gift", "you've received a gift", "claim your gift", "redeem your gift", 
        "accept your gift", "start free trial", "confirm your free trial", "free premium"
    ]
    ACTION_BUTTON_KEYWORDS = [
        "activate", "claim", "start free trial", "redeem now", "accept gift", "try now", "get started"
    ]
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ]

    def __init__(self, **kwargs: Any):
        self.input_file = Path(kwargs['input_file'])
        self.output_dir = Path(kwargs['output_dir'])
        self.delay_min, self.delay_max = kwargs['delay_min'], kwargs['delay_max']
        self.headless = kwargs['headless']
        self.max_retries = kwargs['max_retries']
        self.gui = kwargs['gui_instance']
        self.browser_type = kwargs['browser_type'].lower()
        self.account_switch_threshold = kwargs['account_switch_threshold']
        self.accounts: List[Dict[str, str]] = []
        self.current_account_index, self.links_checked_on_current_account = 0, 0
        self._primary_email: Optional[str] = None
        self._primary_password: Optional[str] = None
        self.running, self.should_stop = False, False
        self.driver: Optional[WebDriver] = None
        self.rate_limit_cooldown_until: Optional[datetime] = None
        self.consecutive_error_count = 0
        self.links_to_process: List[Tuple[str, int, str]] = []
        self.working_links: List[LinkResult] = []
        self.failed_links: List[LinkResult] = []
        self.stats = {'total_processed': 0, 'working_found': 0, 'failed_or_invalid': 0, 'rate_limit_suspected': 0}
        main_file_logger.info(f"Checker initialized for input: {self.input_file}")

    def set_credentials(self, email: str, password: str) -> bool:
        if not email or not password: return False
        self._primary_email, self._primary_password = email, password
        self.accounts = [acc for acc in self.accounts if acc['email'] != email]
        self.accounts.insert(0, {'email': email, 'password': password})
        self.current_account_index = 0
        return True

    def add_additional_account(self, email: str, password: str):
        if not email or not password or email == self._primary_email or any(acc['email'] == email for acc in self.accounts): return
        self.accounts.append({'email': email, 'password': password})
        main_file_logger.info(f"Added additional account to rotation: {email}")

    def _get_current_creds(self) -> Tuple[Optional[str], Optional[str]]:
        if not self.accounts: return None, None
        try: return self.accounts[self.current_account_index]['email'], self.accounts[self.current_account_index]['password']
        except IndexError: return None, None

    def _configure_browser_options(self) -> Optional[Union[ChromeOptions, FirefoxOptions]]:
        if self.browser_type == "chrome":
            options = ChromeOptions()
            if self.headless: options.add_argument("--headless=new")
            options.add_argument(f"user-agent={random.choice(self.USER_AGENTS)}")
            options.add_argument("--disable-gpu"); options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage"); options.add_argument("--log-level=3")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
            return options
        elif self.browser_type == "firefox":
            options = FirefoxOptions()
            if self.headless: options.add_argument("--headless")
            options.set_preference("general.useragent.override", random.choice(self.USER_AGENTS))
            options.set_preference("permissions.default.image", 2)
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference('useAutomationExtension', False)
            return options
        return None

    def _setup_driver(self) -> Optional[WebDriver]:
        if not SELENIUM_AVAILABLE: return None
        main_file_logger.info(f"Setting up {self.browser_type} WebDriver...")
        try:
            options = self._configure_browser_options()
            if not options: return None
            if self.browser_type == "chrome":
                service = ChromeService(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                service = FirefoxService(GeckoDriverManager().install())
                self.driver = webdriver.Firefox(service=service, options=options)
            
            if self.driver:
                self.driver.set_page_load_timeout(45)
                # Anti-detection script
                self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                })
            return self.driver
        except Exception as e:
            main_file_logger.error(f"Error setting up WebDriver: {e}", exc_info=True)
            return None

    def _switch_to_next_account(self) -> bool:
        if len(self.accounts) <= 1: return True
        self.current_account_index = (self.current_account_index + 1) % len(self.accounts)
        new_email, _ = self._get_current_creds()
        if not new_email: return False
        main_file_logger.info(f"Switching to account: {new_email} (Index: {self.current_account_index})")
        self.links_checked_on_current_account = 0
        self._quit_driver()
        return self._setup_driver() and self._login_linkedin()

    def _login_linkedin(self) -> bool:
        email, password = self._get_current_creds()
        if not self.driver or not email or not password: return False
        main_file_logger.info(f"Attempting to log in as {email}...")
        try:
            self.driver.get("https://www.linkedin.com/login")
            username_element = WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, self.LOGIN_USERNAME_ID)))
            username_element.send_keys(email)
            self.driver.find_element(By.ID, self.LOGIN_PASSWORD_ID).send_keys(password)
            self.driver.find_element(By.XPATH, self.LOGIN_SUBMIT_XPATH).click()
            WebDriverWait(self.driver, 30).until(EC.any_of(
                EC.url_contains("feed"), EC.url_contains("checkpoint"),
                EC.presence_of_element_located((By.ID, "error-for-password"))
            ))
            if "feed" in self.driver.current_url: return True
            if "checkpoint" in self.driver.current_url and self.gui and not self.headless:
                self.gui.show_security_challenge_dialog_modal()
                return "feed" in self.driver.current_url
            return False
        except Exception as e:
            main_file_logger.error(f"Error during login for {email}: {e}", exc_info=True)
            return False

    def read_links(self) -> List[Tuple[str, int, str]]:
        self.links_to_process = []
        if not self.input_file.exists(): return []
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if match := re.search(r'https?://[^\s]+', line.strip()):
                    self.links_to_process.append((match.group(0), i + 1, line.strip()))
        if self.gui: self.gui.set_progress_max_value(len(self.links_to_process))
        return self.links_to_process

    def _is_offer_unavailable(self, page_source: str) -> bool:
        return any(kw in page_source.lower() for kw in self.OFFER_UNAVAILABLE_KEYWORDS)

    def _analyze_for_working_trial(self, url: str, page_source: str) -> Tuple[bool, str, str]:
        url_lower, source_lower = url.lower(), page_source.lower()
        if any(kw in source_lower for kw in self.TRIAL_KEYWORDS):
            confidence = "HIGH" if any(p in url_lower for p in ["/redeem", "/gift"]) else "MEDIUM"
            details = "Trial keywords found."
            return True, confidence, details
        return False, "LOW", ""

    def process_single_link(self, url: str, line_num: int, original_line: str) -> LinkResult:
        result_args = {"link": url, "original_url_from_file": original_line, "line_num": line_num}
        if self.should_stop or not self.driver:
            return LinkResult(**result_args, status="CANCELLED" if self.should_stop else "ERROR")
        
        time.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            current_url, page_source = self.driver.current_url, (self.driver.page_source or "").lower()
            result_args["final_url"] = current_url

            if any(kw in page_source for kw in self.RATE_LIMIT_KEYWORDS):
                self.consecutive_error_count += 1
                return LinkResult(**result_args, status="RATE_LIMIT", result_details="Rate limit page.")
            
            if self._is_offer_unavailable(page_source):
                return LinkResult(**result_args, status="FAILED", result_details="Offer unavailable/expired.")
            
            is_working, confidence, details = self._analyze_for_working_trial(current_url, page_source)
            if is_working:
                return LinkResult(**result_args, status="WORKING", confidence=confidence, result_details=details)
            
            return LinkResult(**result_args, status="FAILED", result_details="Inconclusive.")
        except Exception as e:
            self.consecutive_error_count += 1
            return LinkResult(**result_args, status="ERROR", error=f"{type(e).__name__}: {str(e)[:100]}")

    def run(self):
        self.running, self.should_stop = True, False
        if not self.accounts or not self._setup_driver() or not self._login_linkedin():
            self.running = False; self._quit_driver(); return
        
        links_data = self.read_links()
        for url, line_num, original_line in links_data:
            if self.should_stop: break
            if self.consecutive_error_count >= MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN:
                self.rate_limit_cooldown_until = datetime.now() + timedelta(minutes=RATE_LIMIT_COOLDOWN_MINUTES)
                self._switch_to_next_account()
            
            if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
                self.gui.update_status_for_cooldown(True, (self.rate_limit_cooldown_until - datetime.now()).total_seconds())
                time.sleep((self.rate_limit_cooldown_until - datetime.now()).total_seconds())
                self.rate_limit_cooldown_until = None
                self.gui.update_status_for_cooldown(False, 0)
            
            if self.account_switch_threshold > 0 and self.links_checked_on_current_account >= self.account_switch_threshold:
                self._switch_to_next_account()
            
            result = self.process_single_link(url, line_num, original_line)
            self.links_checked_on_current_account += 1
            self.stats['total_processed'] += 1
            if result.status == "WORKING": self.stats['working_found'] += 1; self.working_links.append(result)
            elif result.status == "RATE_LIMIT": self.stats['rate_limit_suspected'] += 1; self.failed_links.append(result)
            elif result.status != "CANCELLED": self.stats['failed_or_invalid'] += 1; self.failed_links.append(result)
            if self.gui:
                self.gui.update_progress(self.stats, self._get_current_creds()[0], self.links_checked_on_current_account, len(self.accounts), result)
        
        self._save_results()
        self._quit_driver()
        self.running = False
        if self.gui: self.gui.process_completed(self.get_output_file_paths())

    def get_output_file_paths(self) -> Dict[str, Optional[str]]:
        base = f"linkedin_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return {
            'working': str(self.output_dir / f"{base}_working.txt") if self.working_links else None,
            'json': str(self.output_dir / f"{base}_detailed.json") if self.working_links or self.failed_links else None
        }

    def _save_results(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths = self.get_output_file_paths()
        if paths['working']:
            with open(paths['working'], 'w', encoding='utf-8') as f:
                for r in self.working_links: f.write(f"{r.final_url or r.link}\n")
        if paths['json']:
            with open(paths['json'], 'w', encoding='utf-8') as f:
                json.dump([asdict(r) for r in self.working_links + self.failed_links], f, indent=2)
        if self.gui: self.gui.result_paths = paths

    def _quit_driver(self):
        if self.driver:
            try: self.driver.quit()
            except Exception: pass
            finally: self.driver = None

    def stop_processing(self): self.should_stop = True

class LinkedInCheckerGUI(ctk.CTk):
    def __init__(self, app_logger: logging.Logger):
        self._setup_theme()
        super().__init__()
        self.app_logger = app_logger
        self.title("LINKIN SOFTWARE")
        self.geometry("1100x800")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.log_queue = queue.Queue()
        self.gui_logger = setup_logging(log_level=logging.INFO, log_queue=self.log_queue)
        self.checker: Optional[EnhancedLinkedInChecker] = None
        self.process_thread: Optional[threading.Thread] = None
        self.result_paths: Dict[str, Optional[str]] = {}
        self.total_links_for_progress: int = 0
        self.gui_additional_accounts: List[Dict[str,str]] = []
        self._initialize_variables()
        self._create_widgets()
        self.check_log_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(10, self.load_config)

    def _setup_theme(self):
        # This method is now corrected to handle potential import errors gracefully.
        try:
            # The correct way to inject a theme is complex and depends on CustomTkinter version.
            # A direct dictionary assignment is often not supported. A safer approach is to use
            # `set_default_color_theme` with a bundled or well-known theme name.
            ctk.set_default_color_theme("green")
            main_file_logger.info("Theme set to 'green'.")
        except Exception as e:
            main_file_logger.error(f"Failed to set theme: {e}. Falling back to default.")
            ctk.set_default_color_theme("blue")

    def _initialize_variables(self):
        self.input_file_var = tk.StringVar(value=DEFAULT_INPUT_FILE)
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.email_var, self.password_var = tk.StringVar(), tk.StringVar()
        self.headless_var = tk.BooleanVar(value=False)
        self.min_delay_var, self.max_delay_var = tk.DoubleVar(value=3.0), tk.DoubleVar(value=5.5)
        self.browser_var, self.max_retries_var = tk.StringVar(value="Chrome"), tk.IntVar(value=2)
        self.additional_account_email_var, self.additional_account_password_var = tk.StringVar(), tk.StringVar()
        self.account_switch_threshold_var = tk.IntVar(value=DEFAULT_ACCOUNT_SWITCH_THRESHOLD)
        self.email_var.trace_add("write", lambda *args: self.update_gui_accounts_list_display())

    def _create_widgets(self):
        ctk.CTkLabel(self, text="LINKIN SOFTWARE", font=("Roboto", 30, "bold")).grid(row=0, column=0, pady=(15, 5))
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main_frame.grid_rowconfigure(0, weight=1); main_frame.grid_columnconfigure(0, weight=1)
        self.tab_view = ctk.CTkTabview(main_frame)
        self.tab_view.grid(row=0, column=0, sticky="nsew")
        tabs = ["Setup", "Accounts", "Configuration", "Logs", "Results"]
        for tab in tabs: self.tab_view.add(tab)
        self._create_setup_tab(self.tab_view.tab("Setup"))
        self._create_accounts_tab(self.tab_view.tab("Accounts"))
        self._create_config_tab(self.tab_view.tab("Configuration"))
        self._create_log_tab(self.tab_view.tab("Logs"))
        self._create_results_tab(self.tab_view.tab("Results"))
        self.tab_view.set("Setup")

    def _create_setup_tab(self, tab: ctk.CTkFrame):
        tab.grid_columnconfigure(0, weight=1)
        # File I/O Frame
        file_frame = ctk.CTkFrame(tab); file_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        file_frame.columnconfigure(1, weight=1)
        self._create_file_input_row(file_frame, "Input Links File:", self.input_file_var, self.browse_input_file, 0)
        self._create_file_input_row(file_frame, "Output Directory:", self.output_dir_var, self.browse_output_dir, 1)
        # Credentials Frame
        cred_frame = ctk.CTkFrame(tab); cred_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(cred_frame, text="Primary Account", font=("Roboto", 16, "bold")).pack(pady=10)
        ctk.CTkEntry(cred_frame, textvariable=self.email_var, placeholder_text="Email").pack(fill="x", padx=10, pady=5)
        ctk.CTkEntry(cred_frame, show="•", textvariable=self.password_var, placeholder_text="Password").pack(fill="x", padx=10, pady=5)
        # Control Buttons Frame
        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.grid(row=2, column=0, sticky="ew", pady=20, padx=10)
        button_frame.columnconfigure((0, 1), weight=1)
        self.start_button = ctk.CTkButton(button_frame, text="Start", height=40, command=self.start_processing)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=5)
        self.stop_button = ctk.CTkButton(button_frame, text="Stop", height=40, state="disabled", command=self.stop_gui_processing)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=5)

    def _create_accounts_tab(self, tab: ctk.CTkFrame):
        tab.grid_columnconfigure((0, 1), weight=1); tab.grid_rowconfigure(0, weight=1)
        # Add Accounts Frame
        add_frame = ctk.CTkFrame(tab); add_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(add_frame, text="Add Accounts", font=("Roboto", 16, "bold")).pack(pady=10)
        ctk.CTkEntry(add_frame, textvariable=self.additional_account_email_var, placeholder_text="Additional Email").pack(fill="x", padx=10, pady=5)
        ctk.CTkEntry(add_frame, show="•", textvariable=self.additional_account_password_var, placeholder_text="Password").pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(add_frame, text="Add Account", command=self.add_gui_account).pack(pady=10, padx=10, fill="x")
        ctk.CTkButton(add_frame, text="Load from File", command=self.load_accounts_from_file).pack(pady=5, padx=10, fill="x")
        # Accounts List Frame
        list_frame = ctk.CTkFrame(tab); list_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        ctk.CTkLabel(list_frame, text="Account Rotation List", font=("Roboto", 16, "bold")).pack(pady=10)
        self.accounts_list_textbox = ctk.CTkTextbox(list_frame, wrap="none", font=("Consolas", 11)); self.accounts_list_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        self.accounts_list_textbox.configure(state="disabled")
        ctk.CTkButton(list_frame, text="Clear Additional Accounts", command=self.clear_gui_additional_accounts).pack(pady=5, padx=10)

    def _create_config_tab(self, tab):
        config_frame = ctk.CTkScrollableFrame(tab); config_frame.pack(fill="both", expand=True, padx=10, pady=10)
        # Browser Settings
        ctk.CTkLabel(config_frame, text="Browser Settings", font=("Roboto", 16, "bold")).pack(anchor="w", pady=(10,5))
        ctk.CTkComboBox(config_frame, values=["Chrome", "Firefox"], variable=self.browser_var).pack(fill="x", pady=5)
        ctk.CTkCheckBox(config_frame, text="Run Headless (no visible browser)", variable=self.headless_var).pack(anchor="w", pady=5)
        # Delay Settings
        ctk.CTkLabel(config_frame, text="Delay Settings (seconds)", font=("Roboto", 16, "bold")).pack(anchor="w", pady=(15,5))
        ctk.CTkEntry(config_frame, textvariable=self.min_delay_var).pack(fill="x", pady=5)
        ctk.CTkEntry(config_frame, textvariable=self.max_delay_var).pack(fill="x", pady=5)
        # Save Button
        ctk.CTkButton(config_frame, text="Save Configuration", command=self.save_config).pack(pady=20)

    def _create_log_tab(self, tab: ctk.CTkFrame):
        tab.rowconfigure(0, weight=1); tab.columnconfigure(0, weight=1)
        self.log_view_ctk = ctk.CTkTextbox(tab, wrap="none", font=("Consolas", 11)); self.log_view_ctk.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.log_view_ctk.configure(state="disabled")
        ctk.CTkButton(tab, text="Clear Log View", command=self.clear_logs).grid(row=1, column=0, pady=5, sticky="e")

    def _create_results_tab(self, tab: ctk.CTkFrame):
        tab.rowconfigure(1, weight=1); tab.columnconfigure(0, weight=1)
        progress_frame = ctk.CTkFrame(tab, fg_color="transparent"); progress_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        progress_frame.columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(progress_frame, text="Progress: Not Started", font=("Roboto", 14, "bold")); self.progress_label.grid(row=0, column=0, pady=(5, 2))
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=18); self.progress_bar.grid(row=1, column=0, pady=2, sticky="ew", padx=10); self.progress_bar.set(0)
        self.stats_label = ctk.CTkLabel(progress_frame, text="Stats: Ready", font=("Roboto", 12)); self.stats_label.grid(row=2, column=0, pady=2)
        self.status_info_label = ctk.CTkLabel(progress_frame, text="", font=("Roboto", 12, "bold")); self.status_info_label.grid(row=3, column=0, pady=2)
        results_tabview = ctk.CTkTabview(tab); results_tabview.grid(row=1, column=0, sticky="nsew", padx=5, pady=0)
        results_tabview.add("Working"); results_tabview.add("Failed/Other")
        self.working_list_ctk = ctk.CTkTextbox(results_tabview.tab("Working"), wrap="none", font=("Consolas", 10), state="disabled"); self.working_list_ctk.pack(fill="both", expand=True, padx=5, pady=5)
        self.failed_list_ctk = ctk.CTkTextbox(results_tabview.tab("Failed/Other"), wrap="none", font=("Consolas", 10), state="disabled"); self.failed_list_ctk.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkButton(tab, text="Open Results Folder", command=self.open_results_folder).grid(row=2, column=0, sticky="w", padx=10, pady=10)

    def set_progress_max_value(self, max_value: int):
        self.after(0, lambda: self._update_progress_max(max_value))
    def _update_progress_max(self, max_value: int):
        self.total_links_for_progress = max_value
        self.progress_bar.set(0)
        self.progress_label.configure(text=f"Progress: 0% (0/{max_value})")

    def update_progress(self, stats: dict, email: Optional[str], links_on_acc: int, total_accs: int, result: LinkResult):
        self.after(0, lambda: self._update_progress_ui(stats, result))
    def _update_progress_ui(self, stats: dict, result: LinkResult):
        if self.total_links_for_progress > 0:
            progress = stats['total_processed'] / self.total_links_for_progress
            self.progress_bar.set(progress)
            self.progress_label.configure(text=f"Progress: {progress:.0%} ({stats['total_processed']}/{self.total_links_for_progress})")
        self.stats_label.configure(text=f"Processed: {stats['total_processed']} | Working: {stats['working_found']} | Failed: {stats['failed_or_invalid']} | Rate-Limited: {stats['rate_limit_suspected']}")
        self._append_result_to_gui(result)

    def _append_result_to_gui(self, result: LinkResult):
        target_listbox = self.working_list_ctk if result.status == "WORKING" else self.failed_list_ctk
        line = f"L{result.line_num:<3}|C:{result.confidence or 'N/A'}|{result.final_url or result.link}\n" if result.status == "WORKING" else f"L{result.line_num:<3}|{result.status:<12}|{result.result_details or result.error or ''}\n"
        target_listbox.configure(state="normal"); target_listbox.insert(tk.END, line); target_listbox.configure(state="disabled")

    def update_status_for_cooldown(self, is_cooldown: bool, duration: float):
        self.after(0, lambda: self._update_cooldown_status(is_cooldown, duration))
    def _update_cooldown_status(self, is_cooldown: bool, duration: float):
        if is_cooldown: self.status_info_label.configure(text=f"Cooldown: Paused for {duration:.0f}s", text_color="orange")
        else: self.status_info_label.configure(text="Resuming...", text_color="lightgreen"); self.after(3000, lambda: self.status_info_label.configure(text=""))

    def process_completed(self, result_paths: Optional[Dict[str, Optional[str]]] = None):
        self.after(0, self._finalize_process_ui)
    def _finalize_process_ui(self):
        self._reset_buttons(); self.title("LINKIN SOFTWARE - Complete"); self.progress_label.configure(text="Progress: Completed")

    def check_log_queue(self):
        try:
            while True: self.log_to_gui(self.log_queue.get_nowait())
        except queue.Empty: pass
        finally: self.after(100, self.check_log_queue)

    def show_error_async(self, message: str):
        self.after(0, lambda: messagebox.showerror("Error", message))

    def show_security_challenge_dialog_modal(self):
        event = threading.Event(); self.after(0, self._create_modal, event); event.wait()
    def _create_modal(self, event: threading.Event):
        top = ctk.CTkToplevel(self); top.title("Action Required"); top.geometry("400x150"); top.transient(self); top.grab_set(); top.attributes("-topmost", True)
        ctk.CTkLabel(top, text="Security Challenge Detected!", font=("Roboto", 14, "bold")).pack(pady=10)
        def on_close(): top.destroy(); event.set()
        ctk.CTkButton(top, text="I'm Done, Continue", command=on_close).pack(pady=20)
        top.protocol("WM_DELETE_WINDOW", on_close)

    def start_processing(self):
        if self.process_thread and self.process_thread.is_alive(): return
        if not self.email_var.get() or not self.password_var.get() or not Path(self.input_file_var.get()).exists():
            self.show_error_async("Primary account and a valid input file are required."); return
        self._reset_ui_for_start()
        try:
            self.checker = EnhancedLinkedInChecker(**self._get_config_as_dict())
            self.checker.set_credentials(self.email_var.get(), self.password_var.get())
            for acc in self.gui_additional_accounts: self.checker.add_additional_account(acc['email'], acc['password'])
            self.process_thread = threading.Thread(target=self.checker.run, daemon=True); self.process_thread.start()
        except Exception as e: self._reset_buttons(); self.log_to_gui(f"Failed to start: {e}")

    def _reset_ui_for_start(self):
        self.start_button.configure(state="disabled"); self.stop_button.configure(state="normal")
        for w in [self.working_list_ctk, self.failed_list_ctk]: w.configure(state="normal"); w.delete("1.0", tk.END); w.configure(state="disabled")

    def stop_gui_processing(self):
        if self.checker: self.checker.stop_processing(); self.stop_button.configure(text="Stopping...", state="disabled")

    def _reset_buttons(self):
        self.start_button.configure(state="normal"); self.stop_button.configure(state="disabled", text="Stop")

    def on_closing(self):
        if self.process_thread and self.process_thread.is_alive():
            if messagebox.askyesno("Confirm Exit", "Process is running. Are you sure you want to exit?"):
                if self.checker: self.checker.stop_processing(); self.process_thread.join(timeout=5.0)
                self.destroy()
        else: self.save_config(); self.destroy()

    def save_config(self):
        try:
            config_data = {key: var.get() for key, var in self._get_variable_map().items()}
            with open(CONFIG_FILE, 'w') as f: json.dump(config_data, f, indent=4)
            self.log_to_gui("Configuration saved.")
        except Exception as e: self.log_to_gui(f"Failed to save config: {e}")

    def load_config(self):
        self.log_to_gui("Attempting to load configuration...")
        if not CONFIG_FILE.exists(): self.log_to_gui("Config file not found."); return
        try:
            with open(CONFIG_FILE, 'r') as f: config = json.load(f)
            for key, var in self._get_variable_map().items():
                if key in config: var.set(config[key])
            self.log_to_gui("Config loaded.")
        except Exception as e: self.log_to_gui(f"Failed to load config: {e}")

    def add_gui_account(self):
        email = self.additional_account_email_var.get().strip()
        password = self.additional_account_password_var.get()
        if email and password and email != self.email_var.get().strip() and not any(acc['email'] == email for acc in self.gui_additional_accounts):
            self.gui_additional_accounts.append({'email': email, 'password': password})
            self.additional_account_email_var.set(""); self.additional_account_password_var.set("")
            self.update_gui_accounts_list_display()

    def clear_gui_additional_accounts(self):
        self.gui_additional_accounts.clear(); self.update_gui_accounts_list_display()

    def update_gui_accounts_list_display(self):
        if hasattr(self, 'accounts_list_textbox'):
            self.accounts_list_textbox.configure(state="normal"); self.accounts_list_textbox.delete("1.0", tk.END)
            if primary_email := self.email_var.get().strip(): self.accounts_list_textbox.insert("end", f"1. {primary_email} (Primary)\n")
            for i, acc in enumerate(self.gui_additional_accounts): self.accounts_list_textbox.insert("end", f"{i + 2}. {acc['email']}\n")
            self.accounts_list_textbox.configure(state="disabled")

    def load_accounts_from_file(self):
        file_path = filedialog.askopenfilename(title="Select Account File", filetypes=[("Text files", "*.txt")])
        if not file_path: return
        loaded, skipped = 0, 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in (line := line.strip()):
                        email, password = [p.strip() for p in line.split(':', 1)]
                        if email and password and email != self.email_var.get().strip() and not any(acc['email'] == email for acc in self.gui_additional_accounts):
                            self.gui_additional_accounts.append({'email': email, 'password': password}); loaded += 1
                        else: skipped += 1
        except Exception as e: self.show_error_async(f"Failed to load accounts: {e}")
        self.update_gui_accounts_list_display()
        messagebox.showinfo("Accounts Loaded", f"Loaded: {loaded}\nSkipped (duplicates/empty): {skipped}")

    def log_to_gui(self, message: str, level: str = "INFO"):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.log_to_gui, message, level); return
        if hasattr(self, 'log_view_ctk'):
            self.log_view_ctk.configure(state="normal")
            self.log_view_ctk.insert(tk.END, message + "\n")
            self.log_view_ctk.configure(state="disabled")
            self.log_view_ctk.see(tk.END)

    def _get_config_as_dict(self):
        config = {key: var.get() for key, var in self._get_variable_map().items()}
        config['gui_instance'] = self
        return config

    def _get_variable_map(self) -> Dict[str, tk.Variable]:
        return {'input_file': self.input_file_var, 'output_dir': self.output_dir_var, 'headless': self.headless_var, 'min_delay': self.min_delay_var, 'max_delay': self.max_delay_var, 'browser': self.browser_var, 'max_retries': self.max_retries_var, 'account_switch_threshold': self.account_switch_threshold_var}

    def _create_file_input_row(self, parent, label, var, cmd, row):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=5)
        ctk.CTkButton(parent, text="Browse...", command=cmd).grid(row=row, column=2, padx=10)

    def browse_input_file(self):
        if fn := filedialog.askopenfilename(title="Select Links File", filetypes=[("Text files", "*.txt")]): self.input_file_var.set(fn)
    def browse_output_dir(self):
        if dn := filedialog.askdirectory(title="Select Output Directory"): self.output_dir_var.set(dn)

    def clear_logs(self):
        self.log_view_ctk.configure(state="normal"); self.log_view_ctk.delete("1.0", tk.END); self.log_view_ctk.configure(state="disabled")

    def open_results_folder(self):
        output_dir = self.output_dir_var.get()
        if not Path(output_dir).is_dir(): self.show_error_async(f"Output directory not found: {output_dir}"); return
        try:
            if sys.platform == 'win32': os.startfile(output_dir)
            elif sys.platform == 'darwin': subprocess.run(['open', output_dir], check=True)
            else: subprocess.run(['xdg-open', output_dir], check=True)
        except Exception as e: self.show_error_async(f"Failed to open folder: {e}")

# --- Main Application Entry Point ---
if __name__ == "__main__":
    try:
        check_prerequisites()
        main_file_logger.info("Application starting...")
        app = LinkedInCheckerGUI(app_logger=main_file_logger)
        app.mainloop()
    except Exception as e:
        main_file_logger.critical(f"Unhandled top-level exception: {e}", exc_info=True)
        try:
            root_fallback = tk.Tk()
            root_fallback.withdraw()
            messagebox.showerror("Fatal Error", f"A critical error occurred: {e}\nCheck logs for details.")
            root_fallback.destroy()
        except Exception as fe:
            print(f"FATAL APPLICATION ERROR: {e}\nFALLBACK DIALOG ERROR: {fe}")
    finally:
        main_file_logger.info("Application finished.")
