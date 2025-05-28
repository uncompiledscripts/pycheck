"""
UPDATES AND IMPROVEMENTS (from original GitHub source and subsequent requests):
- Fixed KeyError: 'border_width' by using a comprehensive theme dictionary (LINKIN_GREEN_THEME) that includes 'border_width' and 'corner_radius' for all relevant CTk widgets, based on search result [1].
- Addressed Pylance type errors for Service objects.
- Corrected mock Selenium class definitions.
- Ensured that if SELENIUM_AVAILABLE is False, _setup_driver returns None early.
- Removed all logo functionality.
- Applied a consistent green/dark green/white theme.
- Added a prominent "LINKIN SOFTWARE" title.
- Ensured webdriver-manager is used.
- Maintained and improved thread safety for all GUI updates.
- Enhanced error handling and logging.
- Refined the security challenge dialog.
- Maintained the critical patch for "unavailable" links.
- Improved account switching logic.
- Ensured progress tracking and status updates are clear.
- Implemented robust file path handling.
- Ensured comprehensive configuration saving and loading.
- Verified Mac and Linux compatibility for opening result folders.
- Standardized string formatting and logging messages.
- Ensured all necessary imports are present and correctly handled.
"""

import requests
import time
import csv
import json
from urllib.parse import urlparse, parse_qs
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any, Callable

# Selenium imports with proper error handling and mocks
try:
    from selenium import webdriver
    from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
    from selenium.webdriver.remote.webelement import WebElement as ActualWebElement
    from selenium.webdriver.common.by import By as ActualBy
    from selenium.webdriver.support.ui import WebDriverWait as ActualWebDriverWait
    from selenium.webdriver.support import expected_conditions as ActualEC
    from selenium.webdriver.chrome.options import Options as ActualChromeOptions
    from selenium.webdriver.firefox.options import Options as ActualFirefoxOptions
    from selenium.webdriver.common.service import Service as BaseSeleniumService
    from selenium.webdriver.chrome.service import Service as ActualChromeSeleniumService
    from webdriver_manager.chrome import ChromeDriverManager as ActualChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager as ActualGeckoDriverManager
    from selenium.webdriver.firefox.service import Service as ActualFirefoxSeleniumService
    from selenium.common.exceptions import TimeoutException as ActualTimeoutException, \
                                           NoSuchElementException as ActualNoSuchElementException, \
                                           WebDriverException as ActualWebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    _initial_logger_fallback = logging.getLogger("InitialFallbackLogger")
    _initial_logger_fallback.setLevel(logging.WARNING)
    if not _initial_logger_fallback.hasHandlers():
        _initial_logger_fallback.addHandler(logging.StreamHandler(sys.stdout))
    _initial_logger_fallback.warning("CRITICAL WARNING: Selenium library or webdriver_manager not found. Web checking functionality will be disabled.")

    class MockOptions:
        def add_argument(self, argument: str): pass
        def add_experimental_option(self, name: str, value: Any): pass
        def set_preference(self, name: str, value: Any): pass

    class MockSeleniumChromeOptions(MockOptions): pass
    class MockSeleniumFirefoxOptions(MockOptions): pass

    class MockSeleniumBy:
        ID = "id"; XPATH = "xpath"; NAME = "name"; CLASS_NAME = "class name"
        LINK_TEXT = "link text"; PARTIAL_LINK_TEXT = "partial link text"
        TAG_NAME = "tag name"; CSS_SELECTOR = "css selector"

    class MockWebElement:
        def send_keys(self, value: str): _initial_logger_fallback.debug(f"MockWebElement.send_keys({value})")
        def click(self): _initial_logger_fallback.debug("MockWebElement.click()")
        def is_displayed(self) -> bool: return True
        @property
        def text(self) -> str: return "mock text"
        def get_attribute(self, name: str) -> Optional[str]: return f"mock_attr_{name}"

    class MockSeleniumWebDriverWait:
        def __init__(self, driver: Any, timeout: float, poll_frequency: float = 0.5, ignored_exceptions: Optional[Any] = None): pass
        def until(self, method: Callable[[Any], Any], message: str = '') -> Any:
            mock_driver_for_method = None
            try: return method(mock_driver_for_method)
            except Exception as e: _initial_logger_fallback.debug(f"Mock until method raised: {e}"); raise MockSeleniumTimeoutException(f"Mock timeout: {message}")
        def until_not(self, method: Callable[[Any], Any], message: str = '') -> Any:
            mock_driver_for_method = None
            try: return not method(mock_driver_for_method)
            except Exception as e: _initial_logger_fallback.debug(f"Mock until_not method raised: {e}"); raise MockSeleniumTimeoutException(f"Mock timeout (not): {message}")

    class MockSeleniumEC:
        @staticmethod
        def presence_of_element_located(locator: Tuple[str, str]) -> Callable[[Any], MockWebElement]: return lambda driver: MockWebElement()
        @staticmethod
        def url_contains(url_substring: str) -> Callable[[Any], bool]: return lambda driver: True
        @staticmethod
        def any_of(*expected_conditions: Callable[[Any], Any]) -> Callable[[Any], Any]:
            def fn(driver: Any) -> Any:
                for cond in expected_conditions:
                    if "presence_of_element_located" in str(cond): return cond(driver)
                if expected_conditions: return expected_conditions[0](driver)
                return True
            return fn

    class MockBaseSeleniumService:
        def __init__(self, executable_path: str = "", port: int = 0, service_args: Optional[List[str]] = None, log_output: Any = None, env: Optional[Dict[str, str]] = None, **extra_kwargs: Any):
            self.executable_path = executable_path
            self.port = port

    class MockActualChromeSeleniumService(MockBaseSeleniumService): pass
    class MockActualFirefoxSeleniumService(MockBaseSeleniumService): pass

    class MockActualChromeDriverManager:
        def install(self) -> str: _initial_logger_fallback.warning("Mock ChromeDriverManager.install() used."); return "mock_chromedriver_path"

    class MockActualGeckoDriverManager:
        def install(self) -> str: _initial_logger_fallback.warning("Mock GeckoDriverManager.install() used."); return "mock_geckodriver_path"

    class MockSeleniumTimeoutException(Exception): pass
    class MockSeleniumNoSuchElementException(Exception): pass
    class MockSeleniumWebDriverException(Exception): pass

    ActualWebElement = MockWebElement
    ActualBy = MockSeleniumBy
    ActualWebDriverWait = MockSeleniumWebDriverWait
    ActualEC = MockSeleniumEC
    ActualChromeOptions = MockSeleniumChromeOptions
    ActualFirefoxOptions = MockSeleniumFirefoxOptions
    BaseSeleniumService = MockBaseSeleniumService
    ActualChromeSeleniumService = MockActualChromeSeleniumService
    ActualFirefoxSeleniumService = MockActualFirefoxSeleniumService
    ActualChromeDriverManager = MockActualChromeDriverManager
    ActualGeckoDriverManager = MockActualGeckoDriverManager
    ActualTimeoutException = MockSeleniumTimeoutException
    ActualNoSuchElementException = MockSeleniumNoSuchElementException
    ActualWebDriverException = MockSeleniumWebDriverException

WebElement = ActualWebElement
By = ActualBy
WebDriverWait = ActualWebDriverWait
EC = ActualEC
ChromeOptions = ActualChromeOptions
FirefoxOptions = ActualFirefoxOptions
ChromeService = ActualChromeSeleniumService
FirefoxService = ActualFirefoxSeleniumService
ChromeDriverManager = ActualChromeDriverManager
GeckoDriverManager = ActualGeckoDriverManager
TimeoutException = ActualTimeoutException
NoSuchElementException = ActualNoSuchElementException
WebDriverException = ActualWebDriverException


from dataclasses import dataclass, asdict, field
from pathlib import Path
import random
from contextlib import contextmanager
import subprocess

import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, scrolledtext

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import queue
import io

# --- Global Variables and Constants ---
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
THEME_FILE_NAME = str(application_path / "linkin_green_theme.json")



# --- ULTIMATE COMPREHENSIVE CustomTkinter Theme (Green/Dark Green/White) ---
# Bulletproof theme covering ALL widgets, internal components, and properties
LINKIN_GREEN_THEME = {
    "CTk": {
        "fg_color": ["#F0F2F5", "#121A12"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkToplevel": {
        "fg_color": ["#F0F2F5", "#121A12"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkFrame": {
        "fg_color": ["#E8F5E9", "#203020"],
        "top_fg_color": ["#D7EED9", "#1A281A"],
        "border_color": ["#388E3C", "#66BB6A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkButton": {
        "fg_color": ["#4CAF50", "#43A047"],
        "hover_color": ["#66BB6A", "#5CB85C"],
        "border_color": ["#388E3C", "#66BB6A"],
        "text_color": ["#FFFFFF", "#E8F5E9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkLabel": {
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "fg_color": ["transparent", "transparent"],
        "corner_radius": 0,
        "border_width": 0
    },
    "CTkEntry": {
        "fg_color": ["#FFFFFF", "#1A281A"],
        "border_color": ["#4CAF50", "#66BB6A"],
        "text_color": ["#1C1C1C", "#E8F5E9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "placeholder_text_color": ["#A5D6A7", "#A5D6A7"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkCheckBox": {
        "checkmark_color": ["#FFFFFF", "#121A12"],
        "fg_color": ["#4CAF50", "#43A047"],
        "border_color": ["#388E3C", "#66BB6A"],
        "hover_color": ["#66BB6A", "#5CB85C"],
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkRadioButton": {
        "fg_color": ["#4CAF50", "#43A047"],
        "border_color": ["#388E3C", "#66BB6A"],
        "hover_color": ["#66BB6A", "#5CB85C"],
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkSwitch": {
        "fg_color": ["#C8E6C9", "#203020"],
        "progress_color": ["#4CAF50", "#66BB6A"],
        "button_color": ["#FFFFFF", "#E8F5E9"],
        "button_hover_color": ["#F5F5F5", "#D0D0D0"],
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkComboBox": {
        "fg_color": ["#FFFFFF", "#1A281A"],
        "border_color": ["#4CAF50", "#66BB6A"],
        "button_color": ["#4CAF50", "#43A047"],
        "button_hover_color": ["#66BB6A", "#5CB85C"],
        "text_color": ["#1C1C1C", "#E8F5E9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "dropdown_fg_color": ["#FFFFFF", "#1A281A"],
        "dropdown_hover_color": ["#E8F5E9", "#2A3A2A"],
        "dropdown_text_color": ["#1C1C1C", "#E8F5E9"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkOptionMenu": {
        "fg_color": ["#4CAF50", "#43A047"],
        "button_color": ["#388E3C", "#66BB6A"],
        "button_hover_color": ["#66BB6A", "#5CB85C"],
        "text_color": ["#FFFFFF", "#E8F5E9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "dropdown_fg_color": ["#FFFFFF", "#1A281A"],
        "dropdown_hover_color": ["#E8F5E9", "#2A3A2A"],
        "dropdown_text_color": ["#1C1C1C", "#E8F5E9"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkSlider": {
        "fg_color": ["#C8E6C9", "#203020"],
        "progress_color": ["#4CAF50", "#66BB6A"],
        "button_color": ["#4CAF50", "#43A047"],
        "button_hover_color": ["#66BB6A", "#5CB85C"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkProgressBar": {
        "fg_color": ["#C8E6C9", "#203020"],
        "progress_color": ["#4CAF50", "#66BB6A"],
        "border_color": ["#388E3C", "#4CAF50"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkTextbox": {
        "fg_color": ["#FBFEFB", "#1A281A"],
        "border_color": ["#66BB6A", "#4CAF50"],
        "text_color": ["#1C1C1C", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "scrollbar_button_color": ["#4CAF50", "#43A047"],
        "scrollbar_button_hover_color": ["#66BB6A", "#5CB85C"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkTabview": {
        "bg_color": ["transparent", "transparent"],
        "border_color": ["#388E3C", "#66BB6A"],
        "fg_color": ["#E8F5E9", "#203020"],
        "segmented_button_fg_color": ["#E8F5E9", "#203020"],
        "segmented_button_selected_color": ["#4CAF50", "#43A047"],
        "segmented_button_selected_hover_color": ["#66BB6A", "#5CB85C"],
        "segmented_button_unselected_color": ["#E8F5E9", "#203020"],
        "segmented_button_unselected_hover_color": ["#D7EED9", "#2A3A2A"],
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkScrollableFrame": {
        "fg_color": ["#E8F5E9", "#203020"],
        "label_fg_color": ["#D7EED9", "#1A281A"],
        "scrollbar_fg_color": ["#C8E6C9", "#203020"],
        "scrollbar_button_color": ["#4CAF50", "#43A047"],
        "scrollbar_button_hover_color": ["#66BB6A", "#5CB85C"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkScrollbar": {
        "fg_color": ["#C8E6C9", "#203020"],
        "button_color": ["#4CAF50", "#43A047"],
        "button_hover_color": ["#66BB6A", "#5CB85C"],
        "scrollbar_button_color": ["#4CAF50", "#43A047"],
        "scrollbar_button_hover_color": ["#66BB6A", "#5CB85C"],
        "border_spacing": 2,
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkSegmentedButton": {
        "fg_color": ["#E8F5E9", "#203020"],
        "selected_color": ["#4CAF50", "#43A047"],
        "selected_hover_color": ["#66BB6A", "#5CB85C"],
        "unselected_color": ["#E8F5E9", "#203020"],
        "unselected_hover_color": ["#D7EED9", "#2A3A2A"],
        "text_color": ["#FFFFFF", "#E8F5E9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    "CTkInputDialog": {
        "fg_color": ["#E8F5E9", "#203020"],
        "text_color": ["#1B5E20", "#C8E6C9"],
        "text_color_disabled": ["#A5D6A7", "#4A754A"],
        "corner_radius": 6,
        "border_width": 1
    },
    # --- INTERNAL COMPONENTS THAT CAUSE KEYERRORS ---
    "DropdownMenu": {  # Used by CTkComboBox and CTkOptionMenu
        "fg_color": ["#FFFFFF", "#1A281A"],
        "hover_color": ["#E8F5E9", "#2A3A2A"],
        "text_color": ["#1C1C1C", "#E8F5E9"],
        "corner_radius": 6,
        "border_width": 1
    },
    # --- FONT DEFINITION ---
    "CTkFont": {
        "family": "Roboto",
        "size": 13,
        "weight": "normal",
        "slant": "roman",
        "underline": False,
        "overstrike": False
    }
}






# --- Logger Setup ---
class QueueHandler(logging.Handler):
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        self.log_queue.put(self.format(record))

def setup_logging(log_level: int = logging.INFO, log_queue: Optional[queue.Queue] = None) -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_format = '%(asctime)s | %(levelname)-8s | %(name)-15s | %(funcName)-20s | Line:%(lineno)-4d | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format, datefmt=date_format)

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        file_handler = logging.FileHandler(
            LOG_DIR / f'linkedin_checker_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except Exception as e:
        print(f"Error setting up file logger: {e}")


    logger_name = "LinkedInCheckerApp"
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setFormatter(formatter)
        handlers.append(queue_handler)
        logger_name = "GUILogger"

    logger_instance = logging.getLogger(logger_name)
    logger_instance.setLevel(log_level)
    if logger_instance.hasHandlers():
        logger_instance.handlers.clear()
    for handler in handlers:
        handler.setLevel(log_level)
        logger_instance.addHandler(handler)
    logger_instance.propagate = False
    return logger_instance

main_file_logger = setup_logging(log_level=logging.INFO)

# --- Prerequisite Checks ---
def check_prerequisites():
    requirements_met = True
    missing_libs = []
    try:
        import customtkinter
        main_file_logger.info("✔ customtkinter is installed")
    except ImportError:
        main_file_logger.error("❌ customtkinter is not installed. Please run: pip install customtkinter")
        missing_libs.append("customtkinter")
        requirements_met = False
    
    if not PIL_AVAILABLE:
        main_file_logger.warning("ℹ Pillow (PIL) not installed. Optional image features (if any) disabled.")
    else:
        main_file_logger.info("✔ Pillow is installed")
    
    if not SELENIUM_AVAILABLE:
        main_file_logger.warning("❌ Selenium and/or webdriver-manager not installed (or import failed). Please run: pip install selenium webdriver-manager")
        main_file_logger.warning("   Web checking functionality will be severely limited or disabled.")
        if "selenium, webdriver-manager" not in missing_libs : missing_libs.append("selenium, webdriver-manager")
        requirements_met = False
    else:
        main_file_logger.info("✔ Selenium and webdriver-manager seem available")

    if not requirements_met:
        error_message = "Some required components are missing:\n\n" + "\n".join(f"- {lib}" for lib in missing_libs)
        error_message += "\n\nPlease install them (e.g., using 'pip install <library_name>') and try again."
        try:
            root_err = tk.Tk()
            root_err.withdraw()
            messagebox.showerror("Prerequisite Error", error_message, parent=None)
            root_err.destroy()
        except tk.TclError:
            print(f"CRITICAL ERROR (Prerequisites): {error_message}")
        sys.exit(1)

# --- Dataclasses ---
@dataclass
class LinkResult:
    link: str
    status: str
    result_details: str = ""
    final_url: Optional[str] = None
    original_url_from_file: Optional[str] = None
    line_num: Optional[int] = None
    confidence: Optional[str] = None
    content_analysis: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

# --- Core Checker Class ---
class EnhancedLinkedInChecker:
    def __init__(self, input_file: str, output_dir: str,
                 delay_min: float, delay_max: float,
                 headless: bool, max_retries: int,
                 account_switch_threshold: int,
                 gui_instance: Optional['LinkedInCheckerGUI'] = None,
                 browser_type: str = "Chrome"):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.headless = headless
        self.max_retries = max_retries
        self.gui = gui_instance
        self.browser_type = browser_type.lower()
        self.account_switch_threshold = account_switch_threshold

        self.accounts: List[Dict[str, str]] = []
        self.current_account_index: int = 0
        self.links_checked_on_current_account: int = 0
        self._primary_email: Optional[str] = None
        self._primary_password: Optional[str] = None

        self.running = False
        self.should_stop = False

        self.links_to_process: List[Tuple[str, int, str]] = []
        self.working_links: List[LinkResult] = []
        self.failed_links: List[LinkResult] = []
        self.stats = {
            'total_processed': 0, 'working_found': 0, 'failed_or_invalid': 0,
            'rate_limit_suspected': 0
        }
        self.driver: Optional[RemoteWebDriver] = None

        self.rate_limit_cooldown_until: Optional[datetime] = None
        self.consecutive_error_count = 0
        self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN = 5
        main_file_logger.info(f"EnhancedLinkedInChecker initialized for file: {self.input_file}")

    def set_credentials(self, email: str, password: str) -> bool:
        if not email or not password:
            main_file_logger.error("Primary email or password cannot be empty.")
            return False
        self._primary_email = email
        self._primary_password = password
        self.accounts = [acc for acc in self.accounts if acc['email'] != email]
        self.accounts.insert(0, {'email': email, 'password': password})
        self.current_account_index = 0
        main_file_logger.info(f"Primary credentials set for: {email}")
        return True

    def add_additional_account(self, email: str, password: str):
        if not email or not password:
            main_file_logger.error("Additional account email or password cannot be empty.")
            return
        if self._primary_email == email:
             main_file_logger.warning(f"Account {email} is already set as primary. Not adding as additional.")
             return
        if any(acc['email'] == email for acc in self.accounts):
            main_file_logger.warning(f"Account {email} is already in the accounts list. Not re-adding.")
            return
        self.accounts.append({'email': email, 'password': password})
        main_file_logger.info(f"Added additional account: {email}")

    def _get_current_creds(self) -> Tuple[Optional[str], Optional[str]]:
        if not self.accounts:
            main_file_logger.error("No accounts configured.")
            return None, None
        if 0 <= self.current_account_index < len(self.accounts):
            acc = self.accounts[self.current_account_index]
            return acc['email'], acc['password']
        main_file_logger.error(f"Current account index {self.current_account_index} out of bounds for {len(self.accounts)} accounts.")
        if self._primary_email and self._primary_password:
            main_file_logger.warning("Resetting to primary account due to invalid index.")
            self.current_account_index = 0
            if self.accounts and self.accounts[0]['email'] == self._primary_email:
                 return self.accounts[0]['email'], self.accounts[0]['password']
        return None, None

    def _setup_driver(self) -> Optional[RemoteWebDriver]:
        if not SELENIUM_AVAILABLE:
            main_file_logger.error("Selenium is not available globally. Cannot setup WebDriver.")
            if self.gui:
                self.gui.show_error_async("Selenium library is not installed. Web checking is disabled.")
            return None
        main_file_logger.info(f"Setting up {self.browser_type} WebDriver using webdriver-manager...")
        try:
            options: Any
            service: Any
            if self.browser_type == "chrome":
                options = ChromeOptions()
                if self.headless:
                    options.add_argument("--headless")
                options.add_argument("--disable-gpu"); options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage"); options.add_argument("--log-level=3")
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
                try:
                    service = ChromeService(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                except Exception as e:
                    main_file_logger.error(f"Failed to start ChromeDriver: {e}", exc_info=True)
                    if self.gui: self.gui.show_error_async(f"Failed to start ChromeDriver: {e}. Check logs.")
                    return None
            elif self.browser_type == "firefox":
                options = FirefoxOptions()
                if self.headless:
                    options.add_argument("--headless")
                options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0")
                try:
                    service = FirefoxService(GeckoDriverManager().install())
                    self.driver = webdriver.Firefox(service=service, options=options)
                except Exception as e:
                    main_file_logger.error(f"Failed to start FirefoxDriver: {e}", exc_info=True)
                    if self.gui: self.gui.show_error_async(f"Failed to start FirefoxDriver: {e}. Check logs.")
                    return None
            else:
                main_file_logger.error(f"Unsupported browser: {self.browser_type}")
                if self.gui: self.gui.show_error_async(f"Unsupported browser: {self.browser_type}")
                return None

            if self.driver:
                self.driver.set_page_load_timeout(45)
                main_file_logger.info(f"{self.browser_type.capitalize()} WebDriver started successfully.")
                return self.driver
            return None
        except Exception as e:
            main_file_logger.error(f"Error setting up WebDriver: {e}", exc_info=True)
            if self.gui: self.gui.show_error_async(f"Error setting up WebDriver: {e}")
            return None

    def _switch_to_next_account(self) -> bool:
        if len(self.accounts) <= 1:
            main_file_logger.info("Only one account configured, no switch possible.")
            return True

        self.current_account_index = (self.current_account_index + 1) % len(self.accounts)
        new_email, _ = self._get_current_creds()

        if not new_email:
            main_file_logger.error("Failed to get credentials for the next account during switch.")
            return False

        main_file_logger.info(f"Attempting to switch to account: {new_email} (Index: {self.current_account_index})")
        self.links_checked_on_current_account = 0
        self._quit_driver()

        if not self._setup_driver():
            main_file_logger.error(f"Failed to set up WebDriver for account {new_email}.")
            return False
        if not self._login_linkedin():
            main_file_logger.error(f"LinkedIn login failed for account {new_email} after switch.")
            if self.gui:
                 self.gui.show_error_async(f"Login failed for account {new_email} after switching. Check credentials/security challenges.")
            return False
        main_file_logger.info(f"Successfully switched and logged in with account: {new_email}")
        return True

    def _login_linkedin(self) -> bool:
        current_email, current_password = self._get_current_creds()
        if not self.driver or not current_email or not current_password:
            main_file_logger.error("Driver not initialized or current account credentials not available for login.")
            return False

        main_file_logger.info(f"Attempting to log in to LinkedIn as {current_email}...")
        try:
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(random.uniform(2.5, 4.5))
            
            username_element: Optional[WebElement] = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            if username_element and hasattr(username_element, 'send_keys'):
                username_element.send_keys(current_email)
            else:
                main_file_logger.error("Username input element not found or invalid for send_keys.")
                return False

            time.sleep(random.uniform(0.6, 1.2))
            password_element = self.driver.find_element(By.ID, "password")
            if password_element and hasattr(password_element, 'send_keys'):
                password_element.send_keys(current_password)
            else:
                main_file_logger.error("Password input element not found or invalid for send_keys.")
                return False
            
            time.sleep(random.uniform(0.6, 1.2))
            submit_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            if submit_button and hasattr(submit_button, 'click'):
                submit_button.click()
            else:
                main_file_logger.error("Submit button not found or invalid for click.")
                return False

            WebDriverWait(self.driver, 30).until(
                EC.any_of(
                    EC.url_contains("feed"), EC.url_contains("checkpoint/challenge"),
                    EC.url_contains("login_verify"), EC.url_contains("login-submit"),
                    EC.presence_of_element_located((By.ID, "error-for-password")),
                    EC.presence_of_element_located((By.ID, "error-for-username")),
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'too many attempts') or contains(text(),'Too many attempts')]"))
                )
            )
            current_url = self.driver.current_url
            page_source_lower = self.driver.page_source.lower()

            if "feed" in current_url:
                main_file_logger.info(f"Login successful for {current_email}.")
                return True
            elif "checkpoint/challenge" in current_url or "login_verify" in current_url:
                main_file_logger.warning(f"LinkedIn security challenge detected for {current_email}.")
                if self.gui and not self.headless:
                    self.gui.show_security_challenge_dialog_modal(self.driver)
                    current_url_after_challenge = self.driver.current_url
                    if "feed" in current_url_after_challenge:
                        main_file_logger.info(f"Login successful for {current_email} after security challenge resolved.")
                        return True
                    else:
                        main_file_logger.error(f"Still not on feed page for {current_email} after security challenge. Current URL: {current_url_after_challenge}. Login failed.")
                        return False
                else:
                    main_file_logger.error(f"Security challenge for {current_email} in headless mode or no GUI. Cannot proceed with this account.")
                    return False
            elif "too many attempts" in page_source_lower or "temporarily restricted" in page_source_lower:
                 main_file_logger.error(f"Login failed for {current_email}: Too many attempts or account restricted.")
                 self.consecutive_error_count += self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN
                 return False
            else:
                error_msg = "Login failed. Unknown reason."
                try:
                    error_element_pass = self.driver.find_element(By.ID, "error-for-password")
                    if error_element_pass and error_element_pass.is_displayed(): error_msg = "Incorrect password."
                except NoSuchElementException: pass
                try:
                    error_element_user = self.driver.find_element(By.ID, "error-for-username")
                    if error_element_user and error_element_user.is_displayed(): error_msg = "Incorrect username."
                except NoSuchElementException: pass
                main_file_logger.error(f"Login failed for {current_email}: {error_msg} Current URL: {current_url}")
                return False
        except TimeoutException:
            main_file_logger.error(f"Timeout during login for {current_email}.")
            if hasattr(self.driver, 'page_source') and self.driver.page_source and "too many login attempts" in self.driver.page_source.lower():
                main_file_logger.error(f"LinkedIn indicates too many login attempts for {current_email}.")
                self.consecutive_error_count += self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN
            return False
        except Exception as e:
            main_file_logger.error(f"An unexpected error occurred during login for {current_email}: {e}", exc_info=True)
            return False

    def read_links(self) -> List[Tuple[str, int, str]]:
        self.links_to_process = []
        if not self.input_file.exists():
            main_file_logger.error(f"Input file not found: {self.input_file}")
            if self.gui:
                self.gui.show_error_async(f"Input file not found: {self.input_file}")
            return []
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                for i, line_content in enumerate(f):
                    original_line_num = i + 1
                    stripped_line = line_content.strip()
                    match = re.search(r'https?://[^\s/$.?#].[^\s]*', stripped_line)
                    if match:
                        self.links_to_process.append((match.group(0), original_line_num, stripped_line))
                    elif stripped_line:
                        main_file_logger.warning(f"No URL found in line {original_line_num}: '{stripped_line}'")
            main_file_logger.info(f"Read {len(self.links_to_process)} URLs from {self.input_file}")
            if self.gui and hasattr(self.gui, 'set_progress_max_value'):
                self.gui.set_progress_max_value(len(self.links_to_process))
            return self.links_to_process
        except Exception as e:
            main_file_logger.error(f"Error reading links file: {e}", exc_info=True)
            if self.gui:
                self.gui.show_error_async(f"Error reading links file: {e}")
            return []

    def process_single_link(self, extracted_url: str, original_line_num: int, original_line_content: str) -> LinkResult:
        current_email, _ = self._get_current_creds()
        main_file_logger.info(f"Processing L#{original_line_num}: {extracted_url} (Account: {current_email or 'N/A'})")
        result_args = {"link": extracted_url, "original_url_from_file": original_line_content, "line_num": original_line_num}

        if self.should_stop:
            return LinkResult(**result_args, status="CANCELLED", result_details="Process cancelled by user")
        if not self.driver:
            return LinkResult(**result_args, status="ERROR", result_details="WebDriver not available")

        time.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            main_file_logger.debug(f"Navigating to: {extracted_url}")
            self.driver.get(extracted_url)
            time.sleep(random.uniform(3.5, 6.0))

            current_url = self.driver.current_url
            page_title = self.driver.title.lower() if self.driver.title else ""
            page_source_lower = self.driver.page_source.lower() if self.driver.page_source else ""
            result_args["final_url"] = current_url
            main_file_logger.debug(f"L{original_line_num} | Title: {page_title[:60]} | URL: {current_url}")

            rate_limit_keywords = ["security verification", "are you a human", "too many requests", "temporarily restricted", "checkpoint", "verify your identity", "unusual activity"]
            if any(kw in page_title for kw in rate_limit_keywords) or any(kw in page_source_lower for kw in rate_limit_keywords):
                main_file_logger.warning(f"Rate limit/security check for {extracted_url} (Title: {page_title})")
                self.consecutive_error_count += 1
                self.stats['rate_limit_suspected'] +=1
                return LinkResult(**result_args, status="RATE_LIMIT_SUSPECTED", result_details=f"Security/Rate limit page (Title: {page_title})")

            if "authwall" in current_url or "login." in current_url or "/login" in current_url:
                main_file_logger.warning(f"Authwall/Login page for {extracted_url}.")
                self.consecutive_error_count +=1
                return LinkResult(**result_args, status="FAILED", result_details="Authwall/Login required or session issue.")

            offer_unavailable_keywords = [
                "offer is no longer available", "this offer has expired", "sorry, this offer isn't available",
                "unable to claim this offer", "this link is no longer active", "link has expired",
                "this gift is no longer available", "this trial is no longer available",
                "you may have already redeemed this gift", "offer already redeemed", "no longer valid",
                "not available at this time", "cannot be claimed", "already been redeemed"
            ]
            normalized_page_source = page_source_lower.replace("’", "'").replace("‘", "'")
            normalized_offer_unavailable_keywords = [kw.replace("’", "'").replace("‘", "'") for kw in offer_unavailable_keywords]

            if any(kw in normalized_page_source for kw in normalized_offer_unavailable_keywords):
                main_file_logger.info(f"Offer unavailable/expired (text match) for {extracted_url}")
                self.consecutive_error_count = 0
                return LinkResult(**result_args, status="FAILED", result_details="Offer unavailable, expired, or already redeemed.")

            gift_redeem_url_patterns = ["/redeem", "/gifts/claim", "/sales/gift/claim", "/premium/redeem", "linkedin.com/checkout/redeem", "linkedin.com/checkout/gift"]
            gift_redeem_query_params = ["redeemToken", "claimToken", "midToken", "msgPayload", "giftId", "trk=li_gift"]
            trial_keywords_on_page = [
                "try premium for free", "start your free month", "1-month free trial", "get premium free",
                "free trial", "claim your free month", "unlock premium free", "try for free", "activate your gift",
                "you've received a gift", "claim your gift", "redeem your gift", "accept your gift",
                "start free trial", "confirm your free trial", "free premium"
            ]
            is_gift_redeem_url = any(patt in current_url.lower() for patt in gift_redeem_url_patterns)
            has_gift_redeem_param = any(qp in current_url for qp in gift_redeem_query_params)
            found_trial_keyword_on_page = any(kw in page_source_lower for kw in trial_keywords_on_page)

            confidence = "LOW"
            details_for_working = "Potential trial/gift indicators found."
            if is_gift_redeem_url and has_gift_redeem_param:
                confidence = "HIGH"
            elif is_gift_redeem_url or has_gift_redeem_param:
                confidence = "MEDIUM"
            elif found_trial_keyword_on_page and ("premium" in current_url.lower() or "checkout" in current_url.lower()):
                 confidence = "MEDIUM"
                 if any(kw in page_title for kw in ["premium", "gift", "trial"]):
                     confidence = "HIGH"

            if (is_gift_redeem_url or has_gift_redeem_param or found_trial_keyword_on_page) and \
               any(qual_url_kw in current_url.lower() for qual_url_kw in ["premium", "gift", "redeem", "checkout", "sales/ ενεργοποίηση-δώρου"]):
                action_button_keywords = ["activate", "claim", "start free trial", "redeem now", "accept gift", "try now", "get started"]
                action_button_found = False
                try:
                    buttons = self.driver.find_elements(By.XPATH, "//button | //a[@role='button'] | //input[@type='submit']")
                    for btn in buttons:
                        btn_text = (btn.text or btn.get_attribute('value') or btn.get_attribute("aria-label") or "").lower()
                        if any(act_kw in btn_text for act_kw in action_button_keywords):
                            action_button_found = True
                            details_for_working += f" Action button: '{btn_text[:30]}'."
                            main_file_logger.info(f"Found action button: '{btn_text[:30]}'")
                            break
                except Exception:
                    pass
                if action_button_found and confidence != "HIGH":
                    confidence = "MEDIUM"

                main_file_logger.info(f"Potential WORKING trial/gift found for: {extracted_url} (Confidence: {confidence})")
                self.consecutive_error_count = 0
                return LinkResult(**result_args, status="WORKING", result_details=details_for_working, confidence=confidence)

            non_trial_url_patterns = ["/feed/", "/my-items/", "/jobs/", "/company/", "/in/", "/notifications/", "/messaging/"]
            if any(patt in current_url.lower() for patt in non_trial_url_patterns) and not \
               (is_gift_redeem_url or has_gift_redeem_param or "premium" in current_url.lower() or "gift" in current_url.lower()):
                 main_file_logger.info(f"Link {extracted_url} is regular LinkedIn page, not trial/gift.")
                 self.consecutive_error_count = 0
                 return LinkResult(**result_args, status="FAILED", result_details="Regular LinkedIn page, not a trial/gift.")

            page_issue_keywords = ["page not found", "content unavailable", "oops, something went wrong", "this page isn't available", "error processing your request"]
            if any(kw in page_source_lower for kw in page_issue_keywords):
                main_file_logger.warning(f"Page issue (not found/error) for {extracted_url}")
                self.consecutive_error_count = 0
                return LinkResult(**result_args, status="FAILED", result_details="Page not found, content unavailable, or processing error.")

            main_file_logger.warning(f"No clear trial/gift or unavailable message for {extracted_url}. Marking FAILED (inconclusive).")
            self.consecutive_error_count = 0
            return LinkResult(**result_args, status="FAILED", result_details="Inconclusive: No specific trial/gift offer or unavailable message detected.")

        except TimeoutException:
            main_file_logger.error(f"Timeout loading link: {extracted_url}")
            self.consecutive_error_count += 1
            return LinkResult(**result_args, status="ERROR", result_details="Timeout loading page.")
        except WebDriverException as e:
            main_file_logger.error(f"WebDriverException for {extracted_url}: {str(e)[:150]}")
            self.consecutive_error_count += 1
            if "target crashed" in str(e).lower() or "session deleted" in str(e).lower() or "disconnected" in str(e).lower():
                main_file_logger.error("WebDriver session crashed/disconnected. Will attempt re-setup or account switch.")
                self._quit_driver()
            return LinkResult(**result_args, status="ERROR", result_details=f"WebDriver error: {str(e)[:100]}")
        except Exception as e:
            main_file_logger.error(f"Unexpected error processing {extracted_url}: {e}", exc_info=True)
            self.consecutive_error_count += 1
            return LinkResult(**result_args, status="ERROR", result_details=f"Unexpected error: {e}")

    def run(self):
        self.running = True
        self.should_stop = False
        self.rate_limit_cooldown_until = None
        self.consecutive_error_count = 0
        self.links_checked_on_current_account = 0
        self.current_account_index = 0
        self.stats = {'total_processed': 0, 'working_found': 0, 'failed_or_invalid': 0, 'rate_limit_suspected': 0}
        self.working_links.clear()
        self.failed_links.clear()


        main_file_logger.info("Starting LinkedIn checking process...")
        if not self.accounts:
            if self._primary_email and self._primary_password:
                 self.accounts.insert(0, {'email': self._primary_email, 'password': self._primary_password})
            else:
                main_file_logger.error("No accounts configured. Aborting.")
                self.running = False
                if self.gui:
                    self.gui.show_error_async("No primary LinkedIn credentials. Cannot start.")
                    self.gui.process_completed()
                return

        links_data = self.read_links()
        if not links_data:
            main_file_logger.warning("No valid URLs to process.")
            self.running = False
            if self.gui:
                self.gui.process_completed()
            return

        if not self._setup_driver() or not self._login_linkedin():
            main_file_logger.error("Initial WebDriver setup or login failed. Aborting.")
            self.running = False
            current_email, _ = self._get_current_creds()
            msg = f"Initial login/setup failed for {current_email or 'primary account'}. Check logs."
            if self.gui:
                self.gui.show_error_async(msg)
                self.gui.process_completed()
            self._quit_driver()
            return

        for extracted_url, original_line_num, original_line_content in links_data:
            if self.should_stop:
                main_file_logger.info("🛑 Process stopped by user request.")
                break

            if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
                remaining_s = (self.rate_limit_cooldown_until - datetime.now()).total_seconds()
                main_file_logger.info(f"Cooldown active. Pausing for {remaining_s:.0f}s...")
                if self.gui:
                    self.gui.update_status_for_cooldown(True, remaining_s)
                time.sleep(remaining_s)
                if self.gui:
                    self.gui.update_status_for_cooldown(False, 0)
                self.rate_limit_cooldown_until = None
                self.consecutive_error_count = 0

            if self.account_switch_threshold > 0 and \
               self.links_checked_on_current_account >= self.account_switch_threshold and \
               len(self.accounts) > 1:
                main_file_logger.info(f"Account switch threshold ({self.account_switch_threshold}) reached. Switching...")
                if not self._switch_to_next_account():
                    main_file_logger.warning("Account switch failed. Continuing with current, or links might fail if login was bad.")
                    if self.gui:
                        self.gui.show_info_async("Account switch failed. Check logs. Processing continues with potential issues.")

            if not self.driver:
                main_file_logger.error("WebDriver unavailable. Attempting re-setup and login.")
                if self._setup_driver() and self._login_linkedin():
                    main_file_logger.info("WebDriver re-initialized.")
                else:
                    main_file_logger.error("Failed to re-initialize WebDriver. Subsequent links for this account will likely fail.")
                    if len(self.accounts) > 1:
                        main_file_logger.info("Attempting another account switch due to critical driver failure.")
                        if not self._switch_to_next_account():
                             main_file_logger.critical("Cannot recover WebDriver or switch account. Stopping processing.")
                             self.should_stop = True
                             if self.gui:
                                 self.gui.show_error_async("Critical WebDriver failure, cannot continue.")
                             break
                    else:
                        main_file_logger.critical("Single account WebDriver re-initialization failed. Stopping.")
                        self.should_stop = True
                        if self.gui:
                            self.gui.show_error_async("WebDriver re-initialization failed for the only account.")
                        break
            
            if self.should_stop:
                break

            result = self.process_single_link(extracted_url, original_line_num, original_line_content)
            self.links_checked_on_current_account += 1
            self.stats['total_processed'] += 1

            if result.status == "WORKING":
                self.stats['working_found'] += 1
                self.working_links.append(result)
            elif result.status == "RATE_LIMIT_SUSPECTED":
                self.stats['rate_limit_suspected'] +=1
                self.failed_links.append(result)
            elif result.status != "CANCELLED":
                self.stats['failed_or_invalid'] += 1
                self.failed_links.append(result)

            if self.gui:
                current_email_disp = self.accounts[self.current_account_index]['email'] if self.accounts and 0 <= self.current_account_index < len(self.accounts) else "N/A"
                self.gui.update_progress(
                    self.stats['total_processed'], self.stats['working_found'],
                    self.stats['failed_or_invalid'] + self.stats['rate_limit_suspected'],
                    current_email_disp, self.links_checked_on_current_account, len(self.accounts)
                )
            main_file_logger.info(f"Result L{original_line_num}: {result.status} - {result.link}")

            if self.consecutive_error_count >= self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN:
                main_file_logger.warning(f"Max consecutive errors ({self.consecutive_error_count}) reached. Cooldown for {RATE_LIMIT_COOLDOWN_MINUTES} min.")
                self.rate_limit_cooldown_until = datetime.now() + timedelta(minutes=RATE_LIMIT_COOLDOWN_MINUTES)
                self.consecutive_error_count = 0
                if self.gui:
                    self.gui.update_status_for_cooldown(True, RATE_LIMIT_COOLDOWN_MINUTES * 60)
                if len(self.accounts) > 1 and self.account_switch_threshold > 0:
                    main_file_logger.info("Attempting account switch due to repeated errors.")
                    if not self._switch_to_next_account():
                        main_file_logger.warning("Account switch after repeated errors failed. Cooldown active.")

        self._save_results()
        self._quit_driver()
        self.running = False
        main_file_logger.info("LinkedIn checking process finished.")
        if self.gui:
            self.gui.process_completed(self.get_output_file_paths())

    def get_output_file_paths(self) -> Dict[str, Optional[str]]:
        base_filename = f"linkedin_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        working_file = self.output_dir / f"{base_filename}_working.txt"
        quick_file = self.output_dir / f"{base_filename}_quick_copy.txt"
        json_file = self.output_dir / f"{base_filename}_detailed.json"
        return {'working_file': str(working_file) if self.working_links else None,
                'quick_file': str(quick_file) if self.working_links else None,
                'json_file': str(json_file) if self.working_links or self.failed_links else None}


    def _save_results(self):
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
            main_file_logger.info(f"Created output dir: {self.output_dir}")
        paths = self.get_output_file_paths()
        all_res = self.working_links + self.failed_links

        working_file_path = paths.get('working_file')
        if working_file_path:
            try:
                with open(working_file_path, 'w', encoding='utf-8') as f:
                    for r in self.working_links:
                        f.write(f"L{r.line_num} | {r.status} | Conf: {r.confidence} | URL: {r.final_url or r.link} | Details: {r.result_details}\n")
                main_file_logger.info(f"Saved {len(self.working_links)} working links to {working_file_path}")
            except Exception as e:
                main_file_logger.error(f"Error saving working links: {e}", exc_info=True)
        
        quick_file_path = paths.get('quick_file')
        if quick_file_path:
            try:
                with open(quick_file_path, 'w', encoding='utf-8') as f:
                    for r in self.working_links:
                        f.write(f"{r.final_url or r.link}\n")
                main_file_logger.info(f"Saved quick copy file to {quick_file_path}")
            except Exception as e:
                main_file_logger.error(f"Error saving quick copy file: {e}", exc_info=True)
        
        json_file_path = paths.get('json_file')
        if json_file_path:
            try:
                serializable_results = [asdict(r, dict_factory=dict) for r in all_res if isinstance(r, LinkResult)]
                if serializable_results:
                    with open(json_file_path, 'w', encoding='utf-8') as f:
                        json.dump(serializable_results, f, indent=2)
                    main_file_logger.info(f"Saved JSON report ({len(serializable_results)} entries) to {json_file_path}")
                else:
                    main_file_logger.info(f"No results to save to JSON file: {json_file_path}")
            except Exception as e:
                main_file_logger.error(f"Error saving JSON report: {e}", exc_info=True)
        if self.gui:
            self.gui.result_paths = paths

    def _quit_driver(self):
        if self.driver:
            try:
                main_file_logger.info("Quitting WebDriver...")
                self.driver.quit()
            except Exception as e:
                main_file_logger.error(f"Error quitting WebDriver: {e}", exc_info=True)
            finally:
                self.driver = None
                main_file_logger.info("WebDriver quit successfully.")

    def stop_processing(self):
        main_file_logger.info("Received stop signal for checker. Attempting to gracefully stop...")
        self.should_stop = True

# --- GUI Class ---
class LinkedInCheckerGUI(ctk.CTk):
    def __init__(self, app_logger: logging.Logger):
        super().__init__()
        self.app_logger = app_logger
        self.title("LINKIN SOFTWARE")
        self.geometry("1050x780")
        self.minsize(1000, 750)

        theme_path = Path(THEME_FILE_NAME)
        if not theme_path.exists():
            try:
                with open(theme_path, "w") as f:
                    json.dump(LINKIN_GREEN_THEME, f, indent=2)
                main_file_logger.info(f"Created theme file: {theme_path}")
            except Exception as e:
                main_file_logger.error(f"Could not create theme file {theme_path}: {e}")

        try:
            if theme_path.exists():
                ctk.set_default_color_theme(str(theme_path))
                main_file_logger.info(f"Applied theme: {theme_path}")
            else:
                main_file_logger.warning(f"Theme file {theme_path} not found. Using default blue theme.")
                ctk.set_default_color_theme("blue")
        except Exception as e:
            main_file_logger.error(f"Failed to apply theme {theme_path}: {e}. Using default blue theme.")
            ctk.set_default_color_theme("blue")


        self.log_queue = queue.Queue()
        self.gui_logger = setup_logging(log_level=logging.INFO, log_queue=self.log_queue)

        self.checker: Optional[EnhancedLinkedInChecker] = None
        self.process_thread: Optional[threading.Thread] = None
        self.result_paths: Dict[str, Optional[str]] = {}
        self.total_links_for_progress: int = 0

        self.input_file_var = tk.StringVar(value=DEFAULT_INPUT_FILE)
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.headless_var = tk.BooleanVar(value=False)
        self.min_delay_var = tk.DoubleVar(value=3.0)
        self.max_delay_var = tk.DoubleVar(value=5.5)
        self.browser_var = tk.StringVar(value="Chrome")
        self.max_retries_var = tk.IntVar(value=2)

        self.additional_account_email_var = tk.StringVar()
        self.additional_account_password_var = tk.StringVar()
        self.account_switch_threshold_var = tk.IntVar(value=DEFAULT_ACCOUNT_SWITCH_THRESHOLD)
        self.gui_additional_accounts: List[Dict[str,str]] = []

        # Explicitly set corner_radius and border_width to 0 for transparent frames
        # if they should not pick up from the theme's CTkFrame defaults.
        self.title_header_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0, border_width=0)
        self.title_header_frame.pack(side="top", fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(self.title_header_frame, text="LINKIN SOFTWARE", font=ctk.CTkFont(size=30, weight="bold")).pack(pady=5)

        self.main_content_frame = ctk.CTkFrame(self) # This will now use theme defaults
        self.main_content_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(0,10))

        self.create_tabs()
        self.load_config()
        self.check_log_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def set_progress_max_value(self, max_value: int):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.set_progress_max_value, max_value)
            return
        self.total_links_for_progress = max_value
        main_file_logger.debug(f"GUI Progress Max Value Set To: {max_value}")
        if hasattr(self, 'progress_bar'):
            if max_value > 0 :
                self.progress_bar.set(0)
                if hasattr(self, 'progress_label'):
                    self.progress_label.configure(text=f"Progress: 0% (0/{max_value})")
            else:
                self.progress_bar.set(0)
                if hasattr(self, 'progress_label'):
                    self.progress_label.configure(text="Progress: No links loaded")
        else:
            main_file_logger.warning("set_progress_max_value called before progress_bar was initialized.")

    def create_tabs(self):
        self.tab_view = ctk.CTkTabview(self.main_content_frame) # Will use theme defaults
        self.tab_view.pack(fill="both", expand=True, pady=(5,0))
        tabs = ["Setup", "Accounts", "Configuration", "Logs", "Results"]
        for tab_name in tabs:
            self.tab_view.add(tab_name)
        self.create_setup_tab(self.tab_view.tab("Setup"))
        self.create_accounts_tab(self.tab_view.tab("Accounts"))
        self.create_config_tab(self.tab_view.tab("Configuration"))
        self.create_log_tab(self.tab_view.tab("Logs"))
        self.create_results_tab(self.tab_view.tab("Results"))
        self.tab_view.set("Setup")

    def create_setup_tab(self, tab: ctk.CTkFrame):
        file_frame = ctk.CTkFrame(tab) # Uses theme
        file_frame.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(file_frame, text="Input Links File:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", pady=5, padx=10)
        ctk.CTkEntry(file_frame, textvariable=self.input_file_var, width=300).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkButton(file_frame, text="Browse", command=self.browse_input_file).grid(row=0, column=2, pady=5, padx=10)
        ctk.CTkLabel(file_frame, text="Output Directory:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=1, column=0, sticky="w", pady=5, padx=10)
        ctk.CTkEntry(file_frame, textvariable=self.output_dir_var, width=300).grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkButton(file_frame, text="Browse", command=self.browse_output_dir).grid(row=1, column=2, pady=5, padx=10)
        file_frame.columnconfigure(1, weight=1)

        cred_frame = ctk.CTkFrame(tab) # Uses theme
        cred_frame.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(cred_frame, text="Primary LinkedIn Account", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5,10))
        ctk.CTkLabel(cred_frame, text="This account will be used first. Add more in 'Accounts' tab for rotation.").pack(pady=(0,10), padx=10, anchor="w")
        ctk.CTkLabel(cred_frame, text="Email:").pack(anchor="w", padx=10)
        ctk.CTkEntry(cred_frame, textvariable=self.email_var).pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(cred_frame, text="Password:").pack(anchor="w", padx=10)
        ctk.CTkEntry(cred_frame, show="•", textvariable=self.password_var).pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(cred_frame, text="Primary email is saved in config, password is not.", font=ctk.CTkFont(size=10)).pack(pady=(0, 5))

        button_frame = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        button_frame.pack(fill="x", pady=20, padx=10)
        self.start_button = ctk.CTkButton(button_frame, text="Start Checking", font=ctk.CTkFont(size=16, weight="bold"), height=40, command=self.start_processing)
        self.start_button.pack(side="left", expand=True, padx=5)
        self.stop_button = ctk.CTkButton(button_frame, text="Stop", font=ctk.CTkFont(size=16, weight="bold"), height=40,
                                         fg_color=("#D32F2F", "#C62828"), hover_color=("#E57373", "#D32F2F"),
                                         command=self.stop_gui_processing, state="disabled")
        self.stop_button.pack(side="left", expand=True, padx=5)

    def create_accounts_tab(self, tab: ctk.CTkFrame):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)

        add_account_frame = ctk.CTkFrame(tab) # Uses theme
        add_account_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        add_account_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(add_account_frame, text="Add Additional Account", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10,15), padx=10)
        ctk.CTkLabel(add_account_frame, text="Email:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(add_account_frame, textvariable=self.additional_account_email_var).grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(add_account_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(add_account_frame, show="•", textvariable=self.additional_account_password_var).grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(add_account_frame, text="Add Account to Session List", command=self.add_gui_account).grid(row=3, column=0, columnspan=2, pady=15, padx=10)
        ctk.CTkLabel(add_account_frame, text="Added accounts are for this session only (not saved).", font=ctk.CTkFont(size=10)).grid(row=4, column=0, columnspan=2, padx=10)

        list_frame = ctk.CTkFrame(tab) # Uses theme
        list_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        list_frame.grid_rowconfigure(1, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(list_frame, text="Session Account List", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=(10,5), padx=10)
        self.accounts_list_textbox = ctk.CTkTextbox(list_frame, height=150, wrap="none", font=("Consolas", 11))
        self.accounts_list_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,5))
        self.accounts_list_textbox.configure(state="disabled")
        ctk.CTkButton(list_frame, text="Clear Additional Accounts", command=self.clear_gui_additional_accounts).grid(row=2, column=0, pady=5, padx=10)

        switch_config_frame = ctk.CTkFrame(tab) # Uses theme
        switch_config_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        switch_config_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(switch_config_frame, text="Account Switching Settings", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10,15), padx=10)
        ctk.CTkLabel(switch_config_frame, text="Switch account after checking:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(switch_config_frame, textvariable=self.account_switch_threshold_var, width=80).grid(row=1, column=1, sticky="w", padx=10, pady=5)
        ctk.CTkLabel(switch_config_frame, text="links. (0 to disable switching).").grid(row=1, column=1, sticky="w", padx=(95,10), pady=5)
        ctk.CTkButton(switch_config_frame, text="Save Threshold (Config Tab for All)", command=self.save_config).grid(row=2, column=0, columnspan=2, pady=15, padx=10)
        self.current_processing_account_label = ctk.CTkLabel(switch_config_frame, text="Current Account: N/A | Links on this account: 0 | Total Accounts: 0", font=ctk.CTkFont(size=12))
        self.current_processing_account_label.grid(row=3, column=0, columnspan=2, pady=(10,5), padx=10)
        self.update_gui_accounts_list_display()

    def add_gui_account(self):
        email = self.additional_account_email_var.get().strip()
        password = self.additional_account_password_var.get()
        if not email or not password:
            self.show_error("Email and Password required for additional accounts.")
            return
        if any(acc['email'] == email for acc in self.gui_additional_accounts):
            self.show_info(f"Account {email} is already in the additional list.")
            return
        if email == self.email_var.get().strip():
            self.show_info(f"Account {email} is the primary. Add a different one.")
            return
        self.gui_additional_accounts.append({'email': email, 'password': password})
        self.additional_account_email_var.set("")
        self.additional_account_password_var.set("")
        self.update_gui_accounts_list_display()
        self.log_to_gui(f"Added additional account {email} to session list.", "INFO")

    def clear_gui_additional_accounts(self):
        self.gui_additional_accounts.clear()
        self.update_gui_accounts_list_display()
        self.log_to_gui("Cleared additional accounts from session list.", "INFO")

    def update_gui_accounts_list_display(self):
        if not hasattr(self, 'accounts_list_textbox'):
            return
        self.accounts_list_textbox.configure(state="normal")
        self.accounts_list_textbox.delete("1.0", tk.END)
        primary_email = self.email_var.get().strip()
        current_total_accounts = 0
        if primary_email:
            self.accounts_list_textbox.insert("end", f"1. {primary_email} (Primary)\n")
            current_total_accounts += 1
        else:
            self.accounts_list_textbox.insert("end", "Primary account (Setup tab) not set.\n")

        for i, acc in enumerate(self.gui_additional_accounts):
            self.accounts_list_textbox.insert("end", f"{i + 1 + current_total_accounts}. {acc['email']} (Additional)\n")

        if not self.gui_additional_accounts and not primary_email:
             self.accounts_list_textbox.insert("end", "\nNo accounts configured for this session.\n")
        elif not self.gui_additional_accounts and primary_email:
             self.accounts_list_textbox.insert("end", "\nNo additional accounts added for this session.\n")
        self.accounts_list_textbox.configure(state="disabled")
        self.update_account_display_info_label("N/A", 0, current_total_accounts + len(self.gui_additional_accounts))

    def update_account_display_info_label(self, current_email: str, links_on_account: int, total_accounts: int):
        if hasattr(self, 'current_processing_account_label'):
            self.current_processing_account_label.configure(
                text=f"Current Account: {current_email} | Links this acc: {links_on_account} | Total Accounts: {total_accounts}"
            )

    def create_config_tab(self, tab: ctk.CTkFrame):
        settings_frame = ctk.CTkScrollableFrame(tab) # Uses theme
        settings_frame.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(settings_frame, text="Browser:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=5, padx=5)
        ctk.CTkComboBox(settings_frame, values=["Chrome", "Firefox"], variable=self.browser_var).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkCheckBox(settings_frame, text="Run in Headless Mode (no visible browser)", variable=self.headless_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=5, padx=5)
        ctk.CTkLabel(settings_frame, text="Request Delay (seconds):", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10,0), padx=5)
        delay_frame = ctk.CTkFrame(settings_frame, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        delay_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=2, padx=5)
        ctk.CTkLabel(delay_frame, text="Min:").pack(side="left", padx=(0,2))
        ctk.CTkEntry(delay_frame, width=70, textvariable=self.min_delay_var).pack(side="left", padx=(0,10))
        ctk.CTkLabel(delay_frame, text="Max:").pack(side="left", padx=(0,2))
        ctk.CTkEntry(delay_frame, width=70, textvariable=self.max_delay_var).pack(side="left")
        ctk.CTkLabel(settings_frame, text="Max Retries per Link:", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w", pady=(10,0), padx=5)
        ctk.CTkEntry(settings_frame, width=70, textvariable=self.max_retries_var).grid(row=4, column=1, sticky="w", pady=(10,0), padx=5)
        ctk.CTkButton(settings_frame, text="Save All Settings", command=self.save_config).grid(row=5, column=0, columnspan=2, pady=20, padx=5)
        help_text_content = ("• Browser: Select browser. Ensure WebDriver is installed or use webdriver-manager.\n"
                           "• Headless Mode: Runs browser invisibly.\n"
                           "• Request Delay: Random delay between links.\n"
                           "• Max Retries: For failed links (basic implementation).\n"
                           "• Account Switch Threshold: In 'Accounts' tab. Saved with 'Save All Settings'.")
        help_textbox = ctk.CTkTextbox(settings_frame, height=120, wrap="word") # Removed border_width=1 to use theme
        help_textbox.grid(row=6, column=0, columnspan=2, sticky="ew", pady=10, padx=5)
        help_textbox.insert("1.0", help_text_content.strip())
        help_textbox.configure(state="disabled")
        settings_frame.columnconfigure(1, weight=1)

    def create_log_tab(self, tab: ctk.CTkFrame):
        log_frame = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_view_ctk = ctk.CTkTextbox(log_frame, wrap="none", height=25, width=100, font=("Consolas", 11))
        self.log_view_ctk.pack(fill="both", expand=True, padx=5, pady=(5,0))
        self.log_view_ctk.configure(state="disabled")
        button_frame = ctk.CTkFrame(log_frame, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        button_frame.pack(fill="x", pady=5)
        ctk.CTkButton(button_frame, text="Clear Logs", command=self.clear_logs).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Save Logs to File", command=self.save_logs_to_file).pack(side="left", padx=5)

    def create_results_tab(self, tab: ctk.CTkFrame):
        progress_frame = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        progress_frame.pack(fill="x", padx=5, pady=(5,10))
        self.progress_label = ctk.CTkLabel(progress_frame, text="Progress: Not Started", font=ctk.CTkFont(size=14, weight="bold"))
        self.progress_label.pack(pady=(5, 2))
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=18)
        self.progress_bar.pack(pady=(0, 5), fill="x", padx=10)
        self.progress_bar.set(0)
        self.status_info_label = ctk.CTkLabel(progress_frame, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.status_info_label.pack(pady=(0,2))
        self.stats_label = ctk.CTkLabel(progress_frame, text="Processed: 0 | Working: 0 | Failed/Other: 0", font=ctk.CTkFont(size=12))
        self.stats_label.pack(pady=(0,5))

        results_display_frame = ctk.CTkFrame(tab) # Uses theme
        results_display_frame.pack(fill="both", expand=True, padx=5, pady=0)
        self.results_tabview = ctk.CTkTabview(results_display_frame) # Uses theme
        self.results_tabview.pack(fill="both", expand=True)
        self.results_tabview.add("Working Trials")
        self.results_tabview.add("Failed/Other Links")
        self.create_result_list_ui(self.results_tabview.tab("Working Trials"), "working")
        self.create_result_list_ui(self.results_tabview.tab("Failed/Other Links"), "failed")
        action_button_frame = ctk.CTkFrame(tab, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        action_button_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(action_button_frame, text="Open Results Folder", command=self.open_results_folder).pack(side="left", padx=5)
        ctk.CTkButton(action_button_frame, text="Export/View Saved Files", command=self.export_results_summary).pack(side="left", padx=5)

    def create_result_list_ui(self, parent_tab: ctk.CTkFrame, list_type: str):
        textbox = ctk.CTkTextbox(parent_tab, wrap="none", font=("Consolas", 10)) # Removed border_width=1 to use theme
        textbox.pack(fill="both", expand=True, padx=5, pady=(5,0))
        textbox.configure(state="disabled")
        if list_type == "working":
            self.working_list_ctk = textbox
        else:
            self.failed_list_ctk = textbox
        button_frame = ctk.CTkFrame(parent_tab, fg_color="transparent", corner_radius=0, border_width=0) # Explicit override
        button_frame.pack(fill="x", pady=2, padx=5)
        ctk.CTkButton(button_frame, text="Copy All to Clipboard", command=lambda lt=list_type: self.copy_all_from_list(lt)).pack(side="left", padx=2)

    def copy_all_from_list(self, list_type: str):
        content = ""
        if list_type == "working" and hasattr(self, 'working_list_ctk'):
            content = self.working_list_ctk.get("1.0", tk.END)
        elif list_type == "failed" and hasattr(self, 'failed_list_ctk'):
            content = self.failed_list_ctk.get("1.0", tk.END)
        if content.strip():
            try:
                self.clipboard_clear()
                self.clipboard_append(content)
                self.log_to_gui(f"Copied {list_type} links.", "INFO")
            except tk.TclError:
                self.log_to_gui("Clipboard access failed.", "ERROR")
                self.show_error("Clipboard access failed.")
        else:
            self.log_to_gui(f"No content in {list_type} list.", "WARNING")

    def browse_input_file(self):
        fn = filedialog.askopenfilename(title="Select Links File", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], initialfile=self.input_file_var.get())
        if fn:
            self.input_file_var.set(fn)

    def browse_output_dir(self):
        dn = filedialog.askdirectory(title="Select Output Directory", initialdir=self.output_dir_var.get())
        if dn:
            self.output_dir_var.set(dn)

    def log_to_gui(self, message: str, level: str = "INFO"):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.log_to_gui, message, level)
            return
        if level:
            formatted_message = f"{datetime.now().strftime('%H:%M:%S')} | {level.upper()}: {message}"
        else:
            formatted_message = message
        if hasattr(self, 'log_view_ctk') and self.log_view_ctk.winfo_exists():
            self.log_view_ctk.configure(state="normal")
            self.log_view_ctk.insert(tk.END, formatted_message + "\n")
            self.log_view_ctk.configure(state="disabled")
            self.log_view_ctk.see(tk.END)
        else:
            print(formatted_message)

    def check_log_queue(self):
        try:
            while True:
                record_str = self.log_queue.get_nowait()
                self.log_to_gui(record_str, level="")
                self.log_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.after(100, self.check_log_queue)

    def clear_logs(self):
        if hasattr(self, 'log_view_ctk') and self.log_view_ctk.winfo_exists():
            self.log_view_ctk.configure(state="normal")
            self.log_view_ctk.delete(1.0, tk.END)
            self.log_view_ctk.configure(state="disabled")
        self.log_to_gui("Log display cleared.", "INFO")

    def save_logs_to_file(self):
        content = ""
        if hasattr(self, 'log_view_ctk') and self.log_view_ctk.winfo_exists():
             content = self.log_view_ctk.get(1.0, tk.END)
        if not content.strip():
            self.show_info("Log is empty, nothing to save.")
            return
        fn = filedialog.asksaveasfilename(title="Save Log File", defaultextension=".log", filetypes=[("Log files", "*.log"), ("Text files", "*.txt")], initialdir=str(LOG_DIR))
        if fn:
            try:
                with open(fn, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.log_to_gui(f"GUI logs saved to {fn}", "INFO")
                self.show_info(f"GUI logs saved to:\n{fn}")
            except Exception as e:
                self.log_to_gui(f"Error saving GUI logs: {e}", "ERROR")
                self.show_error(f"Failed to save GUI logs: {e}")

    def show_error(self, message: str):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.show_error, message)
            return
        self.log_to_gui(message, "ERROR")
        main_file_logger.error(f"GUI Error: {message}")
        if self.winfo_exists():
            messagebox.showerror("Error", message, parent=self)

    def show_error_async(self, message: str):
        self.after(0, self.show_error, message)

    def show_info(self, message: str):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.show_info, message)
            return
        self.log_to_gui(message, "INFO")
        main_file_logger.info(f"GUI Info: {message}")
        if self.winfo_exists():
            messagebox.showinfo("Information", message, parent=self)

    def show_info_async(self, message: str):
        self.after(0, self.show_info, message)

    def show_security_challenge_dialog_modal(self, driver: Optional[RemoteWebDriver]):
        event = threading.Event()
        self.after(0, self._create_and_show_modal_challenge_dialog, event)
        main_file_logger.info("Waiting for security challenge dialog to be resolved by user...")
        event.wait()
        main_file_logger.info("Security challenge dialog closed. Resuming checker.")
        try:
            time.sleep(2)
            if SELENIUM_AVAILABLE and driver:
                WebDriverWait(driver, 300).until_not(EC.url_contains("checkpoint/challenge"))
                WebDriverWait(driver, 15).until_not(EC.url_contains("login_verify"))
        except TimeoutException:
            main_file_logger.warning("Timeout waiting for challenge page to clear after dialog close, or page did not change.")
        except Exception as e:
            main_file_logger.warning(f"Error during post-challenge wait: {e}")


    def _create_and_show_modal_challenge_dialog(self, event_to_set: threading.Event):
        top = ctk.CTkToplevel(self)
        top.attributes("-topmost", True)
        top.title("Security Challenge")
        top.geometry("450x200")
        top.transient(self)
        top.grab_set()
        ctk.CTkLabel(top, text="LinkedIn Security Challenge Detected!", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20,10))
        ctk.CTkLabel(top, text="Please complete the challenge in the browser window.\nThe process will pause.", justify="center").pack(pady=5)
        def on_dialog_close():
            top.destroy()
            event_to_set.set()
        ctk.CTkButton(top, text="Continue (after solving)", command=on_dialog_close).pack(pady=20)
        top.protocol("WM_DELETE_WINDOW", on_dialog_close)

    def open_results_folder(self):
        output_dir_str = self.output_dir_var.get()
        if not Path(output_dir_str).is_dir():
            self.show_error(f"Output directory '{output_dir_str}' not found.")
            return
        try:
            if sys.platform == 'win32':
                os.startfile(output_dir_str)
            elif sys.platform == 'darwin':
                subprocess.run(['open', output_dir_str], check=True)
            else: # Linux and other POSIX
                subprocess.run(['xdg-open', output_dir_str], check=True)
            self.log_to_gui(f"Opened results folder: {output_dir_str}", "INFO")
        except FileNotFoundError:
             self.show_error(f"Could not find command to open folder. Please open manually: {output_dir_str}")
        except Exception as e:
            self.show_error(f"Failed to open results folder: {e}")

    def export_results_summary(self):
        if not self.result_paths or not any(self.result_paths.values()):
            self.show_info("No results saved this session.")
            return
        message = "Session result files:\n\n"
        found_files = False
        for key, path_str in self.result_paths.items():
            if path_str and Path(path_str).exists():
                message += f"- {key.replace('_',' ').title()}: {Path(path_str).name}\n"
                found_files = True
            elif path_str :
                message += f"- {key.replace('_',' ').title()}: (No data for this file)\n"
        
        if not found_files and not any(p for p in self.result_paths.values() if p):
            self.show_info("No result files were generated this session.")
            return
        elif not found_files:
            self.show_info("No data was found to write to result files.")
            return

        folder = Path(self.output_dir_var.get())
        for pv in self.result_paths.values():
            if pv:
                folder = Path(pv).parent
                break
        message += f"\nLocated in: {folder}\n\nOpen this folder?"
        if self.winfo_exists() and messagebox.askyesno("Saved Result Files", message, parent=self) and folder.is_dir():
             self.open_results_folder_explicit(str(folder))
        elif not folder.is_dir():
            self.show_error(f"Target folder '{folder}' not found.")

    def open_results_folder_explicit(self, folder_path: str):
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', folder_path], check=True)
            else:
                subprocess.run(['xdg-open', folder_path], check=True)
            self.log_to_gui(f"Opened folder: {folder_path}", "INFO")
        except FileNotFoundError:
             self.show_error(f"Could not find command to open folder. Please open manually: {folder_path}")
        except Exception as e:
            self.show_error(f"Failed to open folder '{folder_path}': {e}")

    def start_processing(self):
        if self.process_thread and self.process_thread.is_alive():
            self.show_info("A checking process is already running.")
            return
        self.stop_button.configure(state="normal")
        self.start_button.configure(state="disabled")
        self.log_to_gui("Starting processing...", "INFO")
        self.clear_previous_results_display()

        try:
            input_file = self.input_file_var.get().strip()
            output_dir = self.output_dir_var.get().strip()
            primary_email = self.email_var.get().strip()
            primary_password = self.password_var.get()
            if not input_file or not Path(input_file).is_file():
                self.show_error(f"Input file invalid:\n{input_file}")
                self._reset_buttons()
                return
            if not output_dir:
                self.show_error("Output directory needed.")
                self._reset_buttons()
                return
            try:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self.show_error(f"Cannot create/access output dir '{output_dir}':\n{e}")
                self._reset_buttons()
                return
            if not primary_email or not primary_password:
                self.show_error("Primary LinkedIn email and password (in Setup tab) are required.")
                self._reset_buttons()
                return

            self.checker = EnhancedLinkedInChecker(
                input_file=input_file, output_dir=output_dir,
                delay_min=self.min_delay_var.get(), delay_max=self.max_delay_var.get(),
                headless=self.headless_var.get(), max_retries=self.max_retries_var.get(),
                account_switch_threshold=self.account_switch_threshold_var.get(),
                gui_instance=self, browser_type=self.browser_var.get()
            )
            if not self.checker.set_credentials(primary_email, primary_password):
                self.show_error("Failed to set primary credentials. Check logs.")
                self._reset_buttons()
                return
            for acc_data in self.gui_additional_accounts:
                self.checker.add_additional_account(acc_data['email'], acc_data['password'])
            
            total_c_accs = len(self.checker.accounts) if self.checker else 0
            self.update_account_display_info_label(primary_email if total_c_accs > 0 else "N/A", 0, total_c_accs)

            self.process_thread = threading.Thread(target=self.checker.run, daemon=True)
            self.process_thread.start()
        except Exception as e:
            self.show_error(f"Error initializing checker: {e}")
            main_file_logger.error(f"Checker init failed: {e}", exc_info=True)
            self._reset_buttons()

    def _reset_buttons(self):
        if hasattr(self, 'start_button'):
            self.start_button.configure(state="normal")
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state="disabled", text="Stop")

    def clear_previous_results_display(self):
        if hasattr(self,'working_list_ctk'):
            self.working_list_ctk.configure(state="normal")
            self.working_list_ctk.delete("1.0", tk.END)
            self.working_list_ctk.configure(state="disabled")
        if hasattr(self,'failed_list_ctk'):
            self.failed_list_ctk.configure(state="normal")
            self.failed_list_ctk.delete("1.0", tk.END)
            self.failed_list_ctk.configure(state="disabled")
        if hasattr(self,'progress_bar'):
            self.progress_bar.set(0)
        self.total_links_for_progress=0
        if hasattr(self,'stats_label'):
            self.stats_label.configure(text="Processed: 0 | Working: 0 | Failed/Other: 0")
        if hasattr(self,'progress_label'):
            self.progress_label.configure(text="Progress: Not Started")
        self.result_paths = {}
        if hasattr(self,'status_info_label'):
            self.status_info_label.configure(text="")

    def stop_gui_processing(self):
        if self.checker:
            self.log_to_gui("Attempting to stop process...", "INFO")
            self.checker.stop_processing()
            self.stop_button.configure(text="Stopping...", state="disabled")
        else:
            self.log_to_gui("No process running to stop.", "WARNING")
            self._reset_buttons()

    def update_status_for_cooldown(self, is_cooldown: bool, duration_seconds: float):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.update_status_for_cooldown, is_cooldown, duration_seconds)
            return
        if hasattr(self, 'status_info_label'):
            if is_cooldown:
                self.status_info_label.configure(text=f"Rate Limit Cooldown: Paused for {duration_seconds:.0f}s", text_color=("orange", "yellow"))
            else:
                self.status_info_label.configure(text="Cooldown finished. Resuming...", text_color=("green", "lightgreen"))
                self.after(5000, lambda: self.status_info_label.configure(text="") if hasattr(self, 'status_info_label') else None)

    def update_progress(self, total_processed: int, working_found: int, failed_or_invalid: int, current_email: str, links_on_acc: int, total_accs: int):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.update_progress, total_processed, working_found, failed_or_invalid, current_email, links_on_acc, total_accs)
            return
        
        if hasattr(self, 'progress_bar') and hasattr(self, 'progress_label'):
            if self.total_links_for_progress > 0:
                prog_val = total_processed / self.total_links_for_progress
                self.progress_bar.set(prog_val)
                percent = int(prog_val * 100)
                self.progress_label.configure(text=f"Progress: {percent}% ({total_processed}/{self.total_links_for_progress})")
                if self.winfo_exists():
                    self.title(f"LINKIN SOFTWARE - {percent}%")
            else:
                self.progress_label.configure(text=f"Progress: Processing {total_processed}...")
                if self.winfo_exists():
                    self.title("LINKIN SOFTWARE - Processing...")
                self.progress_bar.set(0)

        if hasattr(self, 'stats_label'):
            self.stats_label.configure(text=f"Processed: {total_processed} | Working: {working_found} | Failed/Other: {failed_or_invalid}")
        
        self.update_account_display_info_label(current_email, links_on_acc, total_accs)
        self.update_result_lists_content()

    def update_result_lists_content(self):
        if not self.checker:
            return
        if hasattr(self,'working_list_ctk'):
             self.working_list_ctk.configure(state="normal")
             self.working_list_ctk.delete("1.0", tk.END)
             for item in self.checker.working_links:
                 self.working_list_ctk.insert(tk.END, f"L{item.line_num:<3} | {item.status:<9} | C:{item.confidence or 'N/A':<6} | {item.final_url or item.link} | {item.result_details[:40]}\n")
             self.working_list_ctk.configure(state="disabled")
        if hasattr(self,'failed_list_ctk'):
             self.failed_list_ctk.configure(state="normal")
             self.failed_list_ctk.delete("1.0", tk.END)
             for item in self.checker.failed_links:
                 details = item.result_details or item.error or ""
                 self.failed_list_ctk.insert(tk.END, f"L{item.line_num:<3} | {item.status:<20} | {details[:50]:<50} | {item.final_url or item.link}\n")
             self.failed_list_ctk.configure(state="disabled")

    def process_completed(self, result_paths: Optional[Dict[str, Optional[str]]] = None):
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.process_completed, result_paths)
            return

        self.log_to_gui("✔ Processing finished or stopped.", "INFO")
        if result_paths:
            self.result_paths = result_paths
        self._reset_buttons()
        final_msg = "Completed"
        status_color_tuple = ("green", "lightgreen")
        if self.checker and hasattr(self.checker, 'should_stop') and self.checker.should_stop:
            final_msg = "Stopped by User"
            status_color_tuple = ("orange", "yellow")

        if hasattr(self,'progress_label'):
            self.progress_label.configure(text=f"Progress: {final_msg}")
        if hasattr(self,'status_info_label'):
            self.status_info_label.configure(text=f"Status: {final_msg}", text_color=status_color_tuple)
        if self.winfo_exists():
            self.title("LINKIN SOFTWARE - " + final_msg)

        if self.checker:
            curr_email = "N/A"
            links_acc=0
            tot_accs=len(self.checker.accounts) if hasattr(self.checker,'accounts') else 0
            if self.checker.accounts and 0 <= self.checker.current_account_index < len(self.checker.accounts):
                curr_email=self.checker.accounts[self.checker.current_account_index]['email']
            if hasattr(self.checker, 'links_checked_on_current_account'):
                links_acc = self.checker.links_checked_on_current_account
            
            self.update_progress(
                self.checker.stats['total_processed'], self.checker.stats['working_found'],
                self.checker.stats['failed_or_invalid'] + self.checker.stats.get('rate_limit_suspected',0),
                curr_email, links_acc, tot_accs
            )
            summary = (f"Process {final_msg.lower()}.\n\nTotal: {self.checker.stats['total_processed']}\n"
                       f"Working: {self.checker.stats['working_found']}\nFailed/Other: {self.checker.stats['failed_or_invalid']}\n"
                       f"Rate Limit Suspected: {self.checker.stats.get('rate_limit_suspected',0)}")
            if self.checker.stats['working_found'] > 0:
                if hasattr(self,'results_tabview'):
                    self.results_tabview.set("Working Trials")
                summary += "\n\nView saved files summary?"
                if self.winfo_exists() and messagebox.askyesno(f"Process {final_msg}", summary, parent=self):
                    if hasattr(self,'tab_view'):
                        self.tab_view.set("Results")
                        self.export_results_summary()
            else:
                summary += "\nNo working trials found."
                self.show_info(summary)
        else:
            self.show_info(f"Process {final_msg.lower()}.")
        
        final_total_accs = 0
        if self.checker and hasattr(self.checker,'accounts'):
            final_total_accs = len(self.checker.accounts)
        else:
            final_total_accs = len(self.gui_additional_accounts) + (1 if self.email_var.get() else 0)
        self.update_account_display_info_label("N/A",0,final_total_accs)

    def on_closing(self):
        if self.checker and hasattr(self.checker, 'running') and self.checker.running :
            if self.winfo_exists() and messagebox.askyesno("Confirm Exit", "Process running. Exit anyway?", parent=self):
                if self.checker:
                    self.checker.stop_processing()
                if self.process_thread and self.process_thread.is_alive():
                    main_file_logger.info("Waiting for checker thread to finish upon closing...")
                    self.process_thread.join(timeout=5.0)
                if self.checker and self.checker.driver :
                    self.checker._quit_driver()
                self.destroy()
            else:
                return
        self.save_config()
        if self.checker and self.checker.driver :
            self.checker._quit_driver()
        self.destroy()

    def save_config(self):
        config = {'input_file': self.input_file_var.get(),
                  'output_dir': self.output_dir_var.get(),
                  'primary_email':self.email_var.get(),
                  'headless':self.headless_var.get(),
                  'min_delay':self.min_delay_var.get(),
                  'max_delay':self.max_delay_var.get(),
                  'browser':self.browser_var.get(),
                  'max_retries':self.max_retries_var.get(),
                  'account_switch_threshold':self.account_switch_threshold_var.get()}
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config,f,indent=4)
            self.log_to_gui("Configuration saved.","INFO")
        except Exception as e:
            self.log_to_gui(f"Failed to save configuration: {e}","ERROR")
            main_file_logger.error(f"Failed to save config: {e}", exc_info=True)


    def load_config(self):
        try:
            if Path(CONFIG_FILE).exists():
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                self.input_file_var.set(config.get('input_file', DEFAULT_INPUT_FILE))
                self.output_dir_var.set(config.get('output_dir', DEFAULT_OUTPUT_DIR))
                self.email_var.set(config.get('primary_email', ''))
                self.headless_var.set(config.get('headless', False))
                self.min_delay_var.set(config.get('min_delay', 3.0))
                self.max_delay_var.set(config.get('max_delay', 5.5))
                self.browser_var.set(config.get('browser', 'Chrome'))
                self.max_retries_var.set(config.get('max_retries', 2))
                self.account_switch_threshold_var.set(config.get('account_switch_threshold', DEFAULT_ACCOUNT_SWITCH_THRESHOLD))
                self.log_to_gui("Configuration loaded.", "INFO")
            else:
                self.log_to_gui(f"Config file {CONFIG_FILE} not found. Using defaults.", "INFO")
        except FileNotFoundError:
            self.log_to_gui(f"No config file found at {CONFIG_FILE}. Using defaults.", "INFO")
        except json.JSONDecodeError:
            self.log_to_gui(f"Error decoding config file {CONFIG_FILE}. Using defaults.", "ERROR")
        except Exception as e:
            self.log_to_gui(f"Failed to load config: {e}", "ERROR")
            main_file_logger.error(f"Failed to load config: {e}", exc_info=True)
        self.update_gui_accounts_list_display()

# --- Main Application Entry Point ---
if __name__ == "__main__":
    check_prerequisites()
    main_file_logger.info("Application starting...")
    try:
        app = LinkedInCheckerGUI(app_logger=main_file_logger)
        app.mainloop()
    except Exception as e:
        main_file_logger.critical(f"Unhandled top-level GUI exception: {e}", exc_info=True)
        try:
            root_fallback = tk.Tk()
            root_fallback.withdraw()
            messagebox.showerror("Fatal Error", f"A critical error occurred: {e}\nPlease check the logs in the 'logs' directory for more details.")
            root_fallback.destroy()
        except Exception as fe:
            print(f"FATAL APPLICATION ERROR: {e}")
            print(f"Fallback dialog error: {fe}")
    main_file_logger.info("Application finished.")

