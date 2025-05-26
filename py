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
# It's good practice to handle potential ImportError for Selenium if it's optional or for different environments
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService
    # from webdriver_manager.chrome import ChromeDriverManager # Consider using this for easier driver management
    # For Opera GX or other browsers, you might need their specific Service objects
    # from selenium.webdriver.opera.service import Service as OperaService
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    # Mock Selenium classes if not available, so the rest of the code doesn't break
    class Options: pass
    class By: pass
    class WebDriverWait: pass
    class EC: pass
    class ChromeService: pass
    # class OperaService: pass
    class TimeoutException(Exception): pass
    class NoSuchElementException(Exception): pass
    class WebDriverException(Exception): pass
    print("WARNING: Selenium library not found. Some features will be disabled.")
import getpass
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import random
from contextlib import contextmanager
import subprocess 
# For opening folders

# GUI Imports
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox, scrolledtext
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: Pillow (PIL) library not found. Image features may be disabled.")

import queue
import io

# --- Global Variables and Constants ---
CONFIG_FILE = 'config.json'
LOG_DIR = Path('logs')
DEFAULT_INPUT_FILE = "linkedin_links.txt"
DEFAULT_OUTPUT_DIR = "results"
RATE_LIMIT_COOLDOWN_MINUTES = 5
DEFAULT_ACCOUNT_SWITCH_THRESHOLD = 50 # Default links to check before switching accounts


# --- Logger Setup ---
class QueueHandler(logging.Handler):
    """Custom logging handler to route logs to a GUI queue."""
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord):
        self.log_queue.put(self.format(record))

def setup_logging(log_level=logging.INFO, log_queue: Optional[queue.Queue] = None) -> logging.Logger:
    """Setup enhanced logging."""
    LOG_DIR.mkdir(exist_ok=True)
    log_format = '%(asctime)s | %(levelname)-8s | %(name)-15s | %(funcName)-20s | Line:%(lineno)-4d | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(log_format, datefmt=date_format)

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    file_handler = logging.FileHandler(
        LOG_DIR / f'linkedin_checker_{datetime.now().strftime("%Y%m%d")}.log',
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setFormatter(formatter)
        handlers.append(queue_handler)

    logger_instance = logging.getLogger("LinkedInCheckerApp")
    logger_instance.setLevel(log_level)
    if logger_instance.hasHandlers():
        logger_instance.handlers.clear()
    for handler in handlers:
        handler.setLevel(log_level)
        logger_instance.addHandler(handler)
    logger_instance.propagate = False
    return logger_instance

logger = setup_logging()

# --- Prerequisite Checks ---
def check_prerequisites():
    """Checks for essential libraries and informs the user."""
    requirements_met = True
    missing_libs = []
    try:
        import customtkinter
        logger.info("✔ customtkinter is installed") # Improved: Using actual checkmark
    except ImportError:
        logger.error("❌ customtkinter is not installed. Please run: pip install customtkinter") # Improved: Using actual X
        missing_libs.append("customtkinter")
        requirements_met = False
    if not PIL_AVAILABLE:
        logger.error("❌ Pillow (PIL) is not installed. Please run: pip install Pillow")
        missing_libs.append("Pillow")
        requirements_met = False
    else:
        logger.info("✔ Pillow is installed")
    if not SELENIUM_AVAILABLE:
        logger.warning("❌ Selenium is not installed. Please run: pip install selenium webdriver-manager")
        logger.warning("   Web checking functionality will be severely limited or disabled.")
        missing_libs.append("Selenium (optional but recommended for full functionality)")

    if not requirements_met:
        error_message = "Some required components are missing:\n\n" + "\n".join(f"- {lib}" for lib in missing_libs)
        error_message += "\n\nPlease install them and try again. Check the console for specific commands."
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Prerequisite Error", error_message)
            root.destroy()
        except tk.TclError:
            print(f"CRITICAL ERROR: {error_message}")
        sys.exit(1)

# --- Dataclasses ---
@dataclass
class LinkResult:
    """Holds the result of checking a single link."""
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
    """Handles the core logic of checking LinkedIn links."""
    # Improved: Integrated account switching and refined link processing logic.
    def __init__(self, input_file: str, output_dir: str,
                 delay_min: float, delay_max: float,
                 headless: bool, max_retries: int,
                 account_switch_threshold: int, # New: Threshold for switching accounts
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
        self.account_switch_threshold = account_switch_threshold # New: Store threshold

        # Account management attributes
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
        self.driver: Optional[webdriver.Chrome] = None # Or other browser type

        self.rate_limit_cooldown_until: Optional[datetime] = None
        self.consecutive_error_count = 0
        self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN = 5

        logger.info(f"EnhancedLinkedInChecker initialized for file: {self.input_file}")

    def set_credentials(self, email: str, password: str) -> bool:
        # Improved: Sets primary credentials and ensures it's the first in the account list.
        if not email or not password:
            logger.error("Primary email or password cannot be empty.")
            return False
        self._primary_email = email
        self._primary_password = password
        # Remove any existing account with the same email before adding/prepending
        self.accounts = [acc for acc in self.accounts if acc['email'] != email]
        self.accounts.insert(0, {'email': email, 'password': password})
        self.current_account_index = 0
        logger.info(f"Primary credentials set for: {email}")
        return True

    def add_additional_account(self, email: str, password: str):
        # Improved: Adds more accounts for rotation, avoiding duplicates of primary.
        if not email or not password:
            logger.error("Additional account email or password cannot be empty.")
            return
        if self._primary_email == email:
             logger.warning(f"Account {email} is already set as primary. Not adding as additional.")
             return
        if any(acc['email'] == email for acc in self.accounts):
            logger.warning(f"Account {email} is already in the accounts list. Not re-adding.")
            return
        self.accounts.append({'email': email, 'password': password})
        logger.info(f"Added additional account: {email}")

    def _get_current_creds(self) -> Tuple[Optional[str], Optional[str]]:
        if not self.accounts:
            logger.error("No accounts configured.")
            return None, None
        # Return current account credentials
        return self.accounts[self.current_account_index]['email'], self.accounts[self.current_account_index]['password']

    # The rest of the code for WebDriver setup should be in a separate method, not in _get_current_creds.
    # If you need to setup the driver, call a dedicated method like _setup_driver().

            options: Options
            if self.browser_type == "chrome":
                options = Options()
                if self.headless: options.add_argument("--headless")
                options.add_argument("--disable-gpu"); options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage"); options.add_argument("--log-level=3")
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36")
                try:
                    service = ChromeService()
                    self.driver = webdriver.Chrome(service=service, options=options)
                except WebDriverException as e:
                    logger.error(f"Failed to start ChromeDriver. Ensure it's in PATH or use webdriver-manager. Error: {e}")
                    if self.gui: self.gui.show_error_async(f"Failed to start ChromeDriver: {e}. Check logs.")
                    return None
            elif self.browser_type == "opera gx": # Basic Opera GX setup
                options = webdriver.ChromeOptions() # Opera often uses Chromium options
                if self.headless: options.add_argument('headless')
                # User needs to ensure Opera GX binary path is correctly set if not default
                # And operadriver is in PATH or specified
                # Example: options.binary_location = r"C:\Users\YourUser\AppData\Local\Programs\Opera GX\launcher.exe"
                logger.warning("Opera GX setup assumes operadriver is in PATH and Opera GX is installed in a standard location or binary_location is set in code.")
                try:
                    # Example: service = webdriver.chrome.service.Service(executable_path=r"path\to\operadriver.exe")
                    self.driver = webdriver.Opera(options=options) # Assumes operadriver in PATH
                except WebDriverException as e:
                    logger.error(f"Failed to start OperaDriver. Error: {e}")
                    if self.gui: self.gui.show_error_async(f"Failed to start OperaDriver: {e}. Check logs.")
                    return None
            else:
                logger.error(f"Unsupported browser: {self.browser_type}")
                if self.gui: self.gui.show_error_async(f"Unsupported browser: {self.browser_type}")
                return None

            if self.driver:
                self.driver.set_page_load_timeout(45)
                logger.info(f"{self.browser_type.capitalize()} WebDriver started successfully.")
                return self.driver
            return None
        except Exception as e:
            logger.error(f"Error setting up WebDriver: {e}", exc_info=True)
            if self.gui: self.gui.show_error_async(f"Error setting up WebDriver: {e}")
            return None

    def _login_linkedin(self) -> bool:
        # Improved: Login uses current account from the list.
        current_email, current_password = self._get_current_creds()
        if not self.driver or not current_email or not current_password:
            logger.error("Driver not initialized or current account credentials not available for login.")
            return False

        logger.info(f"Attempting to log in to LinkedIn as {current_email}...")
        try:
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(random.uniform(2.5, 4.5))
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.ID, "username"))).send_keys(current_email)
            time.sleep(random.uniform(0.6, 1.2))
            self.driver.find_element(By.ID, "password").send_keys(current_password)
            time.sleep(random.uniform(0.6, 1.2))
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()

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
                logger.info(f"Login successful for {current_email}.")
                return True
            elif "checkpoint/challenge" in current_url or "login_verify" in current_url:
                logger.warning(f"LinkedIn security challenge detected for {current_email}.")
                if self.gui and not self.headless:
                    # Important: Call GUI dialogs that block until user interaction is done.
                    # This needs to be handled carefully with threading.
                    # For simplicity, a modal dialog is better.
                    self.gui.show_security_challenge_dialog_modal(self.driver) # Assuming this method handles the wait
                    # Re-check URL after user interaction (dialog closes)
                    if "feed" in self.driver.current_url:
                        logger.info(f"Login successful for {current_email} after security challenge resolved.")
                        return True
                logger.error(f"Security challenge for {current_email} not resolved or in headless mode. Login failed.")
                return False
            elif "too many attempts" in page_source_lower or "temporarily restricted" in page_source_lower:
                 logger.error(f"Login failed for {current_email}: Too many attempts or account restricted.")
                 self.consecutive_error_count += self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN
                 return False
            else: # Check for specific login error messages
                error_msg = "Login failed. Unknown reason."
                try:
                    if self.driver.find_element(By.ID, "error-for-password").is_displayed():
                        error_msg = "Incorrect password."
                except NoSuchElementException: pass
                try:
                    if self.driver.find_element(By.ID, "error-for-username").is_displayed():
                        error_msg = "Incorrect username."
                except NoSuchElementException: pass
                logger.error(f"Login failed for {current_email}: {error_msg} Current URL: {current_url}")
                return False
        except TimeoutException:
            logger.error(f"Timeout during login for {current_email}.")
            if hasattr(self.driver, 'page_source') and "too many login attempts" in self.driver.page_source.lower():
                logger.error(f"LinkedIn indicates too many login attempts for {current_email}.")
                self.consecutive_error_count += self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during login for {current_email}: {e}", exc_info=True)
            return False

    def read_links(self) -> List[Tuple[str, int, str]]:
        self.links_to_process = []
        if not self.input_file.exists():
            logger.error(f"Input file not found: {self.input_file}")
            if self.gui: self.gui.show_error_async(f"Input file not found: {self.input_file}")
            return []
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                for i, line_content in enumerate(f):
                    original_line_num = i + 1; stripped_line = line_content.strip()
                    match = re.search(r'https?://[^\s/$.?#].[^\s]*', stripped_line)
                    if match: self.links_to_process.append((match.group(0), original_line_num, stripped_line))
                    elif stripped_line: logger.warning(f"No URL found in line {original_line_num}: '{stripped_line}'")
            logger.info(f"Read {len(self.links_to_process)} URLs from {self.input_file}")
            if self.gui and hasattr(self.gui, 'set_progress_max_value'):
                self.gui.set_progress_max_value(len(self.links_to_process))
            return self.links_to_process
        except Exception as e:
            logger.error(f"Error reading links file: {e}", exc_info=True)
            if self.gui: self.gui.show_error_async(f"Error reading links file: {e}")
            return []

    def process_single_link(self, extracted_url: str, original_line_num: int, original_line_content: str) -> LinkResult:
        # Improved: More robust text analysis for offer status, integrated from previous logic.
        current_email, _ = self._get_current_creds()
        logger.info(f"Processing L#{original_line_num}: {extracted_url} (Account: {current_email or 'N/A'})")
        result_args = {"link": extracted_url, "original_url_from_file": original_line_content, "line_num": original_line_num}

        if self.should_stop: return LinkResult(**result_args, status="CANCELLED", result_details="Process cancelled by user")
        if not self.driver: return LinkResult(**result_args, status="ERROR", result_details="WebDriver not available")

        time.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            logger.debug(f"Navigating to: {extracted_url}")
            self.driver.get(extracted_url)
            time.sleep(random.uniform(3.0, 5.5)) # Allow page to load, consider WebDriverWait for specific elements

            current_url = self.driver.current_url
            page_title = self.driver.title.lower() if self.driver.title else ""
            page_source_lower = self.driver.page_source.lower() if self.driver.page_source else ""
            result_args["final_url"] = current_url
            logger.debug(f"L{original_line_num} | Title: {page_title[:60]} | URL: {current_url}")

            rate_limit_keywords = ["security verification", "are you a human", "too many requests", "temporarily restricted", "checkpoint", "verify your identity", "unusual activity"]
            if any(kw in page_title for kw in rate_limit_keywords) or any(kw in page_source_lower for kw in rate_limit_keywords):
                logger.warning(f"Rate limit/security check for {extracted_url} (Title: {page_title})")
                self.consecutive_error_count += 1; self.stats['rate_limit_suspected'] +=1
                return LinkResult(**result_args, status="RATE_LIMIT_SUSPECTED", result_details=f"Security/Rate limit page (Title: {page_title})")

            if "authwall" in current_url or "login." in current_url or "/login" in current_url:
                 logger.warning(f"Authwall/Login page for {extracted_url}.")
                 self.consecutive_error_count +=1
                 return LinkResult(**result_args, status="FAILED", result_details="Authwall/Login required or session issue.")

            offer_unavailable_keywords = [
                "offer is no longer available", "this offer has expired", "sorry, this offer isn't available",
                "unable to claim this offer", "this link is no longer active", "link has expired",
                "this gift is no longer available", "this trial is no longer available",
                "you may have already redeemed this gift", "offer already redeemed", "no longer valid",
                "not available at this time", "cannot be claimed"
            ]
            if any(kw in page_source_lower for kw in offer_unavailable_keywords):
                logger.info(f"Offer unavailable/expired (text match) for {extracted_url}")
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
            found_trial_keyword = any(kw in page_source_lower for kw in trial_keywords_on_page)

            confidence = "LOW"; details_for_working = "Potential trial/gift indicators found."
            if is_gift_redeem_url and has_gift_redeem_param: confidence = "HIGH"
            elif is_gift_redeem_url or has_gift_redeem_param: confidence = "MEDIUM"
            elif found_trial_keyword and ("premium" in current_url.lower() or "checkout" in current_url.lower()):
                 confidence = "MEDIUM"
                 if any(kw in page_title for kw in ["premium", "gift", "trial"]): confidence = "HIGH"

            if (is_gift_redeem_url or has_gift_redeem_param or found_trial_keyword) and \
               any(qual_url_kw in current_url.lower() for qual_url_kw in ["premium", "gift", "redeem", "checkout", "sales/ ενεργοποίηση-δώρου"]):
                action_button_keywords = ["activate", "claim", "start free trial", "redeem now", "accept gift", "try now", "get started"]
                action_button_found = False
                try:
                    buttons = self.driver.find_elements(By.XPATH, "//button | //a[@role='button'] | //input[@type='submit']")
                    for btn in buttons:
                        btn_text = (btn.text or btn.get_attribute('value') or btn.get_attribute("aria-label") or "").lower()
                        if any(act_kw in btn_text for act_kw in action_button_keywords):
                            action_button_found = True; details_for_working += f" Action button: '{btn_text[:30]}'."; logger.info(f"Found action button: '{btn_text[:30]}'"); break
                except Exception: pass
                if action_button_found and confidence != "HIGH": confidence = "MEDIUM"
                if any(kw in page_source_lower for kw in offer_unavailable_keywords): # Final check for mixed signals
                    logger.warning(f"Mixed signals for {extracted_url}: Working indicators but also 'unavailable' keywords. Marking FAILED.")
                    return LinkResult(**result_args, status="FAILED", result_details="Mixed signals: Offer indicators present but also 'unavailable' text.")

                logger.info(f"Potential WORKING trial/gift found for: {extracted_url} (Confidence: {confidence})")
                self.consecutive_error_count = 0
                return LinkResult(**result_args, status="WORKING", result_details=details_for_working, confidence=confidence)

            non_trial_url_patterns = ["/feed/", "/my-items/", "/jobs/", "/company/", "/in/", "/notifications/", "/messaging/"]
            if any(patt in current_url.lower() for patt in non_trial_url_patterns) and not \
               (is_gift_redeem_url or has_gift_redeem_param or "premium" in current_url.lower() or "gift" in current_url.lower()):
                 logger.info(f"Link {extracted_url} is regular LinkedIn page, not trial/gift.")
                 self.consecutive_error_count = 0
                 return LinkResult(**result_args, status="FAILED", result_details="Regular LinkedIn page, not a trial/gift.")

            page_issue_keywords = ["page not found", "content unavailable", "oops, something went wrong", "this page isn't available", "error processing your request"]
            if any(kw in page_source_lower for kw in page_issue_keywords):
                logger.warning(f"Page issue (not found/error) for {extracted_url}")
                self.consecutive_error_count = 0
                return LinkResult(**result_args, status="FAILED", result_details="Page not found, content unavailable, or processing error.")

            logger.warning(f"No clear trial/gift or unavailable message for {extracted_url}. Marking FAILED (inconclusive).")
            self.consecutive_error_count = 0
            return LinkResult(**result_args, status="FAILED", result_details="Inconclusive: No specific trial/gift offer or unavailable message detected.")
        except TimeoutException:
            logger.error(f"Timeout loading link: {extracted_url}"); self.consecutive_error_count += 1
            return LinkResult(**result_args, status="ERROR", result_details="Timeout loading page.")
        except WebDriverException as e:
            logger.error(f"WebDriverException for {extracted_url}: {str(e)[:150]}"); self.consecutive_error_count += 1
            if "target crashed" in str(e).lower() or "session deleted" in str(e).lower() or "disconnected" in str(e).lower():
                logger.error("WebDriver session crashed/disconnected. Will attempt re-setup or account switch."); self._quit_driver()
            return LinkResult(**result_args, status="ERROR", result_details=f"WebDriver error: {str(e)[:100]}")
        except Exception as e:
            logger.error(f"Unexpected error processing {extracted_url}: {e}", exc_info=True); self.consecutive_error_count += 1
            return LinkResult(**result_args, status="ERROR", result_details=f"Unexpected error: {e}")

    def run(self):
        # Improved: Incorporates account switching logic before processing each link.
        self.running = True; self.should_stop = False
        self.rate_limit_cooldown_until = None; self.consecutive_error_count = 0
        self.links_checked_on_current_account = 0; self.current_account_index = 0

        logger.info("Starting LinkedIn checking process...")
        if not self.accounts: # Ensure primary creds were set and added
            if self._primary_email and self._primary_password:
                 self.accounts.insert(0, {'email': self._primary_email, 'password': self._primary_password})
            else:
                logger.error("No accounts configured. Aborting."); self.running = False
                if self.gui: self.gui.show_error_async_main_thread("No primary LinkedIn credentials. Cannot start."); self.gui.process_completed_main_thread()
                return

        links_data = self.read_links()
        if not links_data:
            logger.warning("No valid URLs to process."); self.running = False
            if self.gui: self.gui.process_completed_main_thread()
            return

        if not self._setup_driver() or not self._login_linkedin():
            logger.error("Initial WebDriver setup or login failed. Aborting."); self.running = False
            current_email, _ = self._get_current_creds()
            msg = f"Initial login/setup failed for {current_email or 'primary account'}. Check logs."
            if self.gui: self.gui.show_error_async_main_thread(msg); self.gui.process_completed_main_thread()
            self._quit_driver(); return

        self.stats = {'total_processed': 0, 'working_found': 0, 'failed_or_invalid': 0, 'rate_limit_suspected': 0}
        self.working_links.clear(); self.failed_links.clear()

        for extracted_url, original_line_num, original_line_content in links_data:
            if self.should_stop: logger.info("🛑 Process stopped by user request."); break

            if self.rate_limit_cooldown_until and datetime.now() > self.rate_limit_cooldown_until and self.account_switch_threshold > 0 and self.links_checked_on_current_account >= self.account_switch_threshold and len(self.accounts) > 1:
                logger.info(f"Account switch threshold ({self.account_switch_threshold}) reached. Switching...")
                if not self._switch_to_next_account():
                    logger.warning("Account switch failed. Continuing with current, or links might fail if login was bad.")
                    if self.gui: self.gui.show_info_async("Account switch failed. Check logs. Processing continues with potential issues.")
                    # If switch fails and driver is None, next block handles it

            if not self.driver: # Driver might be None if it crashed or a switch failed badly
                logger.error("WebDriver unavailable. Attempting re-setup and login.")
                if self._setup_driver() and self._login_linkedin(): logger.info("WebDriver re-initialized.")
                else:
                    logger.error("Failed to re-initialize WebDriver. Subsequent links for this account will likely fail.")
                    # This is bad. Could try another switch if possible or just let errors accumulate
                    if len(self.accounts) > 1:
                        logger.info("Attempting another account switch due to critical driver failure.")
                        if not self._switch_to_next_account():
                             logger.critical("Cannot recover WebDriver or switch account. Stopping processing.")
                             self.should_stop = True # Force stop
                             if self.gui: self.gui.show_error_async_main_thread("Critical WebDriver failure, cannot continue.")
                             break # Exit loop
                    else: # Only one account, and it failed to re-init
                        logger.critical("Single account WebDriver re-initialization failed. Stopping.")
                        self.should_stop = True
                        if self.gui: self.gui.show_error_async_main_thread("WebDriver re-initialization failed for the only account.")
                        break


            result = self.process_single_link(extracted_url, original_line_num, original_line_content)
            self.links_checked_on_current_account += 1

            self.stats['total_processed'] += 1
            if result.status == "WORKING": self.stats['working_found'] += 1; self.working_links.append(result)
            elif result.status == "RATE_LIMIT_SUSPECTED": self.stats['rate_limit_suspected'] +=1; self.failed_links.append(result)
            elif result.status != "CANCELLED": self.stats['failed_or_invalid'] += 1; self.failed_links.append(result)

            if self.gui:
                current_email_disp = self.accounts[self.current_account_index]['email'] if self.accounts else 'N/A'
            if self.consecutive_error_count >= self.MAX_CONSECUTIVE_ERRORS_BEFORE_COOLDOWN:
                logger.warning(f"Max consecutive errors ({self.consecutive_error_count}) reached. Cooldown for {RATE_LIMIT_COOLDOWN_MINUTES} min.")
                self.rate_limit_cooldown_until = datetime.now() + timedelta(minutes=RATE_LIMIT_COOLDOWN_MINUTES)
                self.consecutive_error_count = 0
                if self.gui:
                    self.gui.update_status_for_cooldown_main_thread(True, RATE_LIMIT_COOLDOWN_MINUTES * 60)
                if len(self.accounts) > 1 and self.account_switch_threshold > 0:
                    logger.info("Attempting account switch due to repeated errors.")
                    if not self._switch_to_next_account():
                        logger.warning("Account switch after repeated errors failed. Cooldown active.")


        self._save_results(); self._quit_driver()
        self.running = False; logger.info("LinkedIn checking process finished.")
        if self.gui: self.gui.process_completed_main_thread(self.get_output_file_paths())

    def get_output_file_paths(self) -> Dict[str, Optional[str]]:
        base_filename = f"linkedin_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        working_file = self.output_dir / f"{base_filename}_working.txt"
        quick_file = self.output_dir / f"{base_filename}_quick_copy.txt"
        json_file = self.output_dir / f"{base_filename}_detailed.json"
        return {'working_file': str(working_file) if self.working_links else None,
                'quick_file': str(quick_file) if self.working_links else None,
                'json_file': str(json_file)}

    def _save_results(self):
        if not self.output_dir.exists(): self.output_dir.mkdir(parents=True, exist_ok=True); logger.info(f"Created output dir: {self.output_dir}")
        paths = self.get_output_file_paths(); all_res = self.working_links + self.failed_links
        if self.working_links and paths['working_file']:
            try:
                with open(paths['working_file'], 'w', encoding='utf-8') as f:
                    for r in self.working_links: f.write(f"L{r.line_num} | {r.status} | Conf: {r.confidence} | URL: {r.final_url or r.link} | Details: {r.result_details}\n")
                logger.info(f"Saved {len(self.working_links)} working links to {paths['working_file']}")
            except Exception as e: logger.error(f"Error saving working links: {e}", exc_info=True)
        if self.working_links and paths['quick_file']:
            try:
                with open(paths['quick_file'], 'w', encoding='utf-8') as f:
                    for r in self.working_links: f.write(f"{r.final_url or r.link}\n")
                logger.info(f"Saved quick copy file to {paths['quick_file']}")
            except Exception as e: logger.error(f"Error saving quick copy file: {e}", exc_info=True)
        if paths['json_file']:
            try:
                serializable = [asdict(r) for r in all_res if isinstance(r, LinkResult)]
                with open(paths['json_file'], 'w', encoding='utf-8') as f: json.dump(serializable, f, indent=2)
                logger.info(f"Saved JSON report ({len(serializable)} entries) to {paths['json_file']}")
            except Exception as e: logger.error(f"Error saving JSON report: {e}", exc_info=True)
        if self.gui: self.gui.result_paths = paths

    def _quit_driver(self):
        if self.driver:
            try: logger.info("Quitting WebDriver..."); self.driver.quit()
            except Exception as e: logger.error(f"Error quitting WebDriver: {e}", exc_info=True)
            finally: self.driver = None; logger.info("WebDriver quit successfully.")

    def stop_processing(self):
        logger.info("Received stop signal. Attempting to gracefully stop...")
        self.should_stop = True

    def start_processing(self):
        if self.process_thread and self.process_thread.is_alive():
            self.log_to_gui("A checking process is already running.", level="WARNING")
            return
        self.stop_button.configure(state="normal")
        self.start_button.configure(state="disabled")
        self.should_stop = False
        def run_checker():
            try:
                input_file = self.input_file_var.get()
                output_dir = self.output_dir_var.get()
                email = self.email_var.get()
                password = self.password_var.get()
                headless = self.headless_var.get()
                min_delay = self.min_delay_var.get()
                max_delay = self.max_delay_var.get()
                browser = self.browser_var.get()
                max_retries = self.max_retries_var.get()
                account_switch_threshold = self.account_switch_threshold_var.get()
                self.checker = EnhancedLinkedInChecker(
                    input_file=input_file,
                    output_dir=output_dir,
                    delay_min=min_delay,
                    delay_max=max_delay,
                    headless=headless,
                    max_retries=max_retries,
                    account_switch_threshold=account_switch_threshold,
                    gui_instance=self,
                    browser_type=browser
                )
                self.checker.set_credentials(email, password)
                self.checker.read_links()
                self.checker.running = True
                self.checker.process_links()
            except Exception as e:
                self.log_to_gui(f"Error during processing: {e}", level="ERROR")
            finally:
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
        self.process_thread = threading.Thread(target=run_checker, daemon=True)
        self.process_thread.start()

# --- GUI Class ---
class LinkedInCheckerGUI(ctk.CTk):
    def __init__(self, app_logger: logging.Logger):
        super().__init__()
        self.app_logger = app_logger
        self.title("LinkedIn Trial Checker")
        self.geometry("1000x750") # Increased size for Accounts tab
        self.minsize(950, 700)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.log_queue = queue.Queue()
        self.gui_logger = setup_logging(log_queue=self.log_queue)

        self.checker: Optional[EnhancedLinkedInChecker] = None
        self.process_thread: Optional[threading.Thread] = None
        self.result_paths: Dict[str, Optional[str]] = {}
        self.total_links_for_progress: int = 0

        self.input_file_var = tk.StringVar(value=DEFAULT_INPUT_FILE)
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.email_var = tk.StringVar() # Primary email
        self.password_var = tk.StringVar() # Primary password
        self.headless_var = tk.BooleanVar(value=False)
        self.min_delay_var = tk.DoubleVar(value=3.0)
        self.max_delay_var = tk.DoubleVar(value=5.5)
        self.browser_var = tk.StringVar(value="Chrome")
        self.max_retries_var = tk.IntVar(value=2)

        # Account Tab Variables - New
        self.additional_account_email_var = tk.StringVar()
        self.additional_account_password_var = tk.StringVar()
        self.account_switch_threshold_var = tk.IntVar(value=DEFAULT_ACCOUNT_SWITCH_THRESHOLD)
        self.gui_additional_accounts: List[Dict[str,str]] = []

        self.main_frame = ctk.CTkFrame(self); self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.create_tabs()
        self.load_config()
        self.check_log_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def set_progress_max_value(self, max_value: int):
        self.total_links_for_progress = max_value
        logger.debug(f"GUI Progress Max Value Set To: {max_value}")
        if max_value > 0 :
            self.progress_bar.set(0)
            self.progress_label.configure(text=f"Progress: 0% (0/{max_value})")
        else:
            self.progress_bar.set(0)
            self.progress_label.configure(text="Progress: No links loaded")

    def create_tabs(self):
        self.tab_view = ctk.CTkTabview(self.main_frame)
        self.tab_view.pack(fill="both", expand=True, pady=(0,5))
        tabs = ["Setup", "Accounts", "Configuration", "Logs", "Results"] # New: Accounts tab
        for tab_name in tabs: self.tab_view.add(tab_name)
        self.create_setup_tab(self.tab_view.tab("Setup"))
        self.create_accounts_tab(self.tab_view.tab("Accounts")) # New: Create accounts tab
        self.create_config_tab(self.tab_view.tab("Configuration"))
        self.create_log_tab(self.tab_view.tab("Logs"))
        self.create_results_tab(self.tab_view.tab("Results"))
        self.tab_view.set("Setup")


    def create_setup_tab(self, tab: ctk.CTkFrame):
        header_frame = ctk.CTkFrame(tab, fg_color="transparent")
        header_frame.pack(fill="x", pady=(10, 15), padx=10)
        ctk.CTkLabel(header_frame, text="LinkedIn Trial Checker", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(0,5))
        ctk.CTkLabel(header_frame, text="Check LinkedIn URLs for valid premium trial offers", font=ctk.CTkFont(size=14)).pack()

        file_frame = ctk.CTkFrame(tab); file_frame.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(file_frame, text="Input Links File:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w", pady=5, padx=10)
        ctk.CTkEntry(file_frame, textvariable=self.input_file_var, width=300).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkButton(file_frame, text="Browse", command=self.browse_input_file).grid(row=0, column=2, pady=5, padx=10)
        ctk.CTkLabel(file_frame, text="Output Directory:", font=ctk.CTkFont(size=14, weight="bold")).grid(row=1, column=0, sticky="w", pady=5, padx=10)
        ctk.CTkEntry(file_frame, textvariable=self.output_dir_var, width=300).grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkButton(file_frame, text="Browse", command=self.browse_output_dir).grid(row=1, column=2, pady=5, padx=10)
        file_frame.columnconfigure(1, weight=1)

        cred_frame = ctk.CTkFrame(tab); cred_frame.pack(fill="x", pady=10, padx=10)
        ctk.CTkLabel(cred_frame, text="Primary LinkedIn Account", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(5,10))
        ctk.CTkLabel(cred_frame, text="This account will be used first. Add more in 'Accounts' tab for rotation.").pack(pady=(0,10), padx=10, anchor="w")
        ctk.CTkLabel(cred_frame, text="Email:").pack(anchor="w", padx=10)
        ctk.CTkEntry(cred_frame, textvariable=self.email_var).pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(cred_frame, text="Password:").pack(anchor="w", padx=10)
        ctk.CTkEntry(cred_frame, show="•", textvariable=self.password_var).pack(fill="x", padx=10, pady=(0, 5)) # Fixed: Using actual bullet
        ctk.CTkLabel(cred_frame, text="Primary email is saved in config, password is not.", font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(0, 5))

        button_frame = ctk.CTkFrame(tab, fg_color="transparent"); button_frame.pack(fill="x", pady=20, padx=10)
        self.start_button = ctk.CTkButton(button_frame, text="Start Checking", font=ctk.CTkFont(size=16, weight="bold"), height=40, command=self.start_processing)
        self.start_button.pack(side="left", expand=True, padx=5)
        self.stop_button = ctk.CTkButton(button_frame, text="Stop", font=ctk.CTkFont(size=16, weight="bold"), height=40, fg_color="darkred", hover_color="#C00000", command=self.stop_processing, state="disabled")
        self.stop_button.pack(side="left", expand=True, padx=5)

    def create_accounts_tab(self, tab: ctk.CTkFrame):
        # New: GUI for managing multiple accounts and switch threshold.
        tab.grid_columnconfigure(0, weight=1); tab.grid_columnconfigure(1, weight=1)

        add_account_frame = ctk.CTkFrame(tab); add_account_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        add_account_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(add_account_frame, text="Add Additional Account", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10,15), padx=10)
        ctk.CTkLabel(add_account_frame, text="Email:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(add_account_frame, textvariable=self.additional_account_email_var).grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(add_account_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(add_account_frame, show="•", textvariable=self.additional_account_password_var).grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(add_account_frame, text="Add Account to Session List", command=self.add_gui_account).grid(row=3, column=0, columnspan=2, pady=15, padx=10)
        ctk.CTkLabel(add_account_frame, text="Added accounts are for this session only (not saved).", font=ctk.CTkFont(size=10), text_color="gray").grid(row=4, column=0, columnspan=2, padx=10)

        list_frame = ctk.CTkFrame(tab); list_frame.grid(row=0, column=1, rowspan=2, padx=10, pady=10, sticky="nsew")
        list_frame.grid_rowconfigure(1, weight=1); list_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(list_frame, text="Session Account List", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=(10,5), padx=10)
        self.accounts_list_textbox = ctk.CTkTextbox(list_frame, height=150, wrap="none", font=("Consolas", 11))
        self.accounts_list_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,5))
        self.accounts_list_textbox.insert("end", "Primary account (Setup tab) is used first.\nAdditional accounts appear here.\n")
        self.accounts_list_textbox.configure(state="disabled")
        ctk.CTkButton(list_frame, text="Clear Additional Accounts", command=self.clear_gui_additional_accounts).grid(row=2, column=0, pady=5, padx=10)

        switch_config_frame = ctk.CTkFrame(tab); switch_config_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        switch_config_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(switch_config_frame, text="Account Switching Settings", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(10,15), padx=10)
        ctk.CTkLabel(switch_config_frame, text="Switch account after checking:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ctk.CTkEntry(switch_config_frame, textvariable=self.account_switch_threshold_var, width=80).grid(row=1, column=1, sticky="w", padx=10, pady=5)
        ctk.CTkLabel(switch_config_frame, text="links. (0 to disable switching).").grid(row=1, column=1, sticky="w", padx=(95,10), pady=5) # Adjusted text
        ctk.CTkButton(switch_config_frame, text="Save Threshold (Config Tab for All)", command=self.save_config).grid(row=2, column=0, columnspan=2, pady=15, padx=10) # Clarified button
        self.current_processing_account_label = ctk.CTkLabel(switch_config_frame, text="Current Account: N/A | Links on this account: 0 | Total Accounts: 0", font=ctk.CTkFont(size=12))
        self.current_processing_account_label.grid(row=3, column=0, columnspan=2, pady=(10,5), padx=10)
        self.update_gui_accounts_list_display() # Initialize display

    def add_gui_account(self):
        # New: Adds an account to the GUI's session list.
        email = self.additional_account_email_var.get().strip()
        password = self.additional_account_password_var.get()
        if not email or not password: self.show_error("Email and Password required for additional accounts."); return
        if any(acc['email'] == email for acc in self.gui_additional_accounts):
            self.show_info(f"Account {email} is already in the additional list."); return
        if email == self.email_var.get().strip():
            self.show_info(f"Account {email} is the primary. Add a different one."); return
        self.gui_additional_accounts.append({'email': email, 'password': password})
        self.additional_account_email_var.set(""); self.additional_account_password_var.set("")
        self.update_gui_accounts_list_display()
        self.log_to_gui(f"Added additional account {email} to session list.", "INFO")

    def clear_gui_additional_accounts(self):
        # New: Clears session-specific additional accounts.
        self.gui_additional_accounts.clear()
        self.update_gui_accounts_list_display()
        self.log_to_gui("Cleared additional accounts from session list.", "INFO")

    def update_gui_accounts_list_display(self):
        # New: Updates the textbox showing configured accounts.
        if not hasattr(self, 'accounts_list_textbox'): return # Not initialized yet
        self.accounts_list_textbox.configure(state="normal"); self.accounts_list_textbox.delete("1.0", tk.END)
        primary_email = self.email_var.get().strip()
        total_accounts_in_gui = 0
        if primary_email:
            self.accounts_list_textbox.insert("end", f"1. {primary_email} (Primary)\n")
            total_accounts_in_gui += 1
        else: self.accounts_list_textbox.insert("end", "Primary account (Setup tab) not set.\n")
        for i, acc in enumerate(self.gui_additional_accounts):
            self.accounts_list_textbox.insert("end", f"{i + total_accounts_in_gui + (1 if not primary_email and not total_accounts_in_gui else 0)}. {acc['email']} (Additional)\n") # Ensure numbering is correct
        if not self.gui_additional_accounts and not primary_email:
             self.accounts_list_textbox.insert("end", "\nNo accounts configured for this session.\n")
        elif not self.gui_additional_accounts and primary_email:
             self.accounts_list_textbox.insert("end", "\nNo additional accounts added for this session.\n")
        self.accounts_list_textbox.configure(state="disabled")
        self.update_account_display_info_label("N/A", 0, total_accounts_in_gui + len(self.gui_additional_accounts))


    def update_account_display_info_label(self, current_email: str, links_on_account: int, total_accounts: int):
        # New: Updates the label in Accounts tab footer showing current processing account.
        if hasattr(self, 'current_processing_account_label'):
            self.current_processing_account_label.configure(
                text=f"Current Account: {current_email} | Links this acc: {links_on_account} | Total Accounts: {total_accounts}"
            )

    def create_config_tab(self, tab: ctk.CTkFrame):
        settings_frame = ctk.CTkScrollableFrame(tab); settings_frame.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(settings_frame, text="Browser:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=5, padx=5)
        ctk.CTkComboBox(settings_frame, values=["Chrome", "Opera GX"], variable=self.browser_var).grid(row=0, column=1, sticky="ew", pady=5, padx=5)
        ctk.CTkCheckBox(settings_frame, text="Run in Headless Mode (no visible browser)", variable=self.headless_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=5, padx=5)
        ctk.CTkLabel(settings_frame, text="Request Delay (seconds):", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10,0), padx=5)
        delay_frame = ctk.CTkFrame(settings_frame, fg_color="transparent"); delay_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=2, padx=5)
        ctk.CTkLabel(delay_frame, text="Min:").pack(side="left", padx=(0,2)); ctk.CTkEntry(delay_frame, width=70, textvariable=self.min_delay_var).pack(side="left", padx=(0,10))
        ctk.CTkLabel(delay_frame, text="Max:").pack(side="left", padx=(0,2)); ctk.CTkEntry(delay_frame, width=70, textvariable=self.max_delay_var).pack(side="left")
        ctk.CTkLabel(settings_frame, text="Max Retries per Link:", font=ctk.CTkFont(weight="bold")).grid(row=4, column=0, sticky="w", pady=(10,0), padx=5)
        ctk.CTkEntry(settings_frame, width=70, textvariable=self.max_retries_var).grid(row=4, column=1, sticky="w", pady=(10,0), padx=5)
        ctk.CTkButton(settings_frame, text="Save All Settings", command=self.save_config).grid(row=5, column=0, columnspan=2, pady=20, padx=5)
        help_text_content = ("• Browser: Select browser. Ensure WebDriver is installed.\n"
                           "• Headless Mode: Runs browser invisibly.\n"
                           "• Request Delay: Random delay between links.\n"
                           "• Max Retries: For failed links (basic implementation).\n"
                           "• Account Switch Threshold: In 'Accounts' tab. Saved with 'Save All Settings'.") # Fixed bullet, updated info
        help_textbox = ctk.CTkTextbox(settings_frame, height=120, wrap="word", border_width=1); help_textbox.grid(row=6, column=0, columnspan=2, sticky="ew", pady=10, padx=5)
        help_textbox.insert("1.0", help_text_content.strip()); help_textbox.configure(state="disabled")
        settings_frame.columnconfigure(1, weight=1)


    def create_log_tab(self, tab: ctk.CTkFrame):
        log_frame = ctk.CTkFrame(tab, fg_color="transparent"); log_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_view_ctk = ctk.CTkTextbox(log_frame, wrap="none", height=25, width=100, font=("Consolas", 11))
        self.log_view_ctk.pack(fill="both", expand=True, padx=5, pady=(5,0)); self.log_view_ctk.configure(state="disabled")
        button_frame = ctk.CTkFrame(log_frame, fg_color="transparent"); button_frame.pack(fill="x", pady=5)
        ctk.CTkButton(button_frame, text="Clear Logs", command=self.clear_logs).pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Save Logs to File", command=self.save_logs_to_file).pack(side="left", padx=5)

    def create_results_tab(self, tab: ctk.CTkFrame):
        progress_frame = ctk.CTkFrame(tab, fg_color="transparent"); progress_frame.pack(fill="x", padx=5, pady=(5,10))
        self.progress_label = ctk.CTkLabel(progress_frame, text="Progress: Not Started", font=ctk.CTkFont(size=14, weight="bold"))
        self.progress_label.pack(pady=(5, 2))
        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=18); self.progress_bar.pack(pady=(0, 5), fill="x", padx=10); self.progress_bar.set(0)
        self.status_info_label = ctk.CTkLabel(progress_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="orange")
        self.status_info_label.pack(pady=(0,2))
        self.stats_label = ctk.CTkLabel(progress_frame, text="Processed: 0 | Working: 0 | Failed/Other: 0", font=ctk.CTkFont(size=12))
        self.stats_label.pack(pady=(0,5))

        results_display_frame = ctk.CTkFrame(tab); results_display_frame.pack(fill="both", expand=True, padx=5, pady=0)
        self.results_tabview = ctk.CTkTabview(results_display_frame); self.results_tabview.pack(fill="both", expand=True)
        self.results_tabview.add("Working Trials"); self.results_tabview.add("Failed/Other Links")
        self.create_result_list_ui(self.results_tabview.tab("Working Trials"), "working")
        self.create_result_list_ui(self.results_tabview.tab("Failed/Other Links"), "failed")
        action_button_frame = ctk.CTkFrame(tab, fg_color="transparent"); action_button_frame.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(action_button_frame, text="Open Results Folder", command=self.open_results_folder).pack(side="left", padx=5)
        ctk.CTkButton(action_button_frame, text="Export/View Saved Files", command=self.export_results_summary).pack(side="left", padx=5)

    def create_result_list_ui(self, parent_tab: ctk.CTkFrame, list_type: str):
        textbox = ctk.CTkTextbox(parent_tab, wrap="none", font=("Consolas", 10), border_width=1)
        textbox.pack(fill="both", expand=True, padx=5, pady=(5,0)); textbox.configure(state="disabled")
        if list_type == "working": self.working_list_ctk = textbox
        else: self.failed_list_ctk = textbox
        button_frame = ctk.CTkFrame(parent_tab, fg_color="transparent"); button_frame.pack(fill="x", pady=2, padx=5)
        ctk.CTkButton(button_frame, text="Copy All to Clipboard", command=lambda lt=list_type: self.copy_all_from_list(lt)).pack(side="left", padx=2)

    def copy_all_from_list(self, list_type: str):
        content = ""
        if list_type == "working" and hasattr(self, 'working_list_ctk'): content = self.working_list_ctk.get("1.0", tk.END)
        elif list_type == "failed" and hasattr(self, 'failed_list_ctk'): content = self.failed_list_ctk.get("1.0", tk.END)
        if content.strip():
            try: self.clipboard_clear(); self.clipboard_append(content); self.log_to_gui(f"Copied {list_type} links.", "INFO")
            except tk.TclError: self.log_to_gui("Clipboard access failed.", "ERROR"); self.show_error("Clipboard access failed.")
        else: self.log_to_gui(f"No content in {list_type} list.", "WARNING")

    def browse_input_file(self):
        fn = filedialog.askopenfilename(title="Select Links File", filetypes=[("Text files", "*.txt"), ("All files", "*.*")], initialfile=self.input_file_var.get())
        if fn: self.input_file_var.set(fn)

    def browse_output_dir(self):
        dn = filedialog.askdirectory(title="Select Output Directory", initialdir=self.output_dir_var.get())
        if dn: self.output_dir_var.set(dn)

    def log_to_gui(self, message: str, level: str = "INFO"):
        # Ensure this runs on the main thread if called from another thread.
        if threading.current_thread() is not threading.main_thread():
            self.after(0, self.log_to_gui, message, level)
            return
        formatted_message = f"{datetime.now().strftime('%H:%M:%S')} | {level.upper()}: {message}"
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert(tk.END, formatted_message + "\n")
        self.log_textbox.configure(state="disabled")
        self.log_textbox.see(tk.END)

    def update_progress(self, total_processed, working_found, failed_or_invalid, current_email, links_on_acc, total_accs):
        if self.total_links_for_progress:
            prog_val = total_processed / self.total_links_for_progress
            self.progress_bar.set(prog_val)
            percent = int(prog_val * 100)
            self.progress_label.configure(text=f"Progress: {percent}% ({total_processed}/{self.total_links_for_progress})")
            if self.winfo_exists(): self.title(f"Checker - {percent}%")
        else:
            self.progress_label.configure(text=f"Progress: Processing {total_processed}...")
            if self.winfo_exists(): self.title(f"Checker - Processing...")
            self.progress_bar.set(0)
        self.stats_label.configure(text=f"Processed: {total_processed} | Working: {working_found} | Failed/Other: {failed_or_invalid}")
        self.update_account_display_info_label(current_email, links_on_acc, total_accs)
        self.update_result_lists_content()

    def update_result_lists_content(self):
        if not self.checker: return
        self.working_list_ctk.configure(state="normal"); self.working_list_ctk.delete("1.0", tk.END)
        for item in self.checker.working_links:
            self.working_list_ctk.insert(tk.END, f"L{item.line_num}: {item.url}\n")
        self.working_list_ctk.configure(state="disabled")
        # Repeat for failed_list_ctk if needed
        current_total_accs = len(self.checker.accounts) if self.checker and self.checker.accounts else (1 if self.email_var.get() else 0) + len(self.gui_additional_accounts)
        self.update_account_display_info_label("N/A", 0, current_total_accs)


    def on_closing(self):
        if self.checker and self.checker.running:
            if self.winfo_exists() and messagebox.askyesno("Confirm Exit", "Process running. Exit anyway?", parent=self):
                self.checker.stop_processing()
                if self.process_thread and self.process_thread.is_alive(): self.process_thread.join(timeout=3.0)
                if self.checker and self.checker.driver: self.checker._quit_driver()
                self.destroy()
            else: return
        self.save_config()
        if self.checker and self.checker.driver: self.checker._quit_driver()
        self.destroy()

    def save_config(self):
        # Improved: Saves account_switch_threshold and primary_email.
        config = {'input_file': self.input_file_var.get(), 'output_dir': self.output_dir_var.get(),
                  'primary_email': self.email_var.get(), # Save primary email
                  'headless': self.headless_var.get(),
                  'min_delay': self.min_delay_var.get(), 'max_delay': self.max_delay_var.get(),
                  'browser': self.browser_var.get(), 'max_retries': self.max_retries_var.get(),
                  'account_switch_threshold': self.account_switch_threshold_var.get()} # Save threshold
        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(config, f, indent=4)
            self.log_to_gui("Configuration saved.", "INFO")
        except Exception as e: self.log_to_gui(f"Failed to save configuration: {e}", "ERROR")

    def load_config(self):
        # Improved: Loads account_switch_threshold and primary_email.
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: config = json.load(f)
                self.input_file_var.set(config.get('input_file', DEFAULT_INPUT_FILE))
                self.output_dir_var.set(config.get('output_dir', DEFAULT_OUTPUT_DIR))
                self.email_var.set(config.get('primary_email', '')) # Load primary email
                self.headless_var.set(config.get('headless', False))
                self.min_delay_var.set(config.get('min_delay', 3.0))
                self.max_delay_var.set(config.get('max_delay', 5.5))
                self.browser_var.set(config.get('browser', 'Chrome'))
                self.max_retries_var.set(config.get('max_retries', 2))
                self.account_switch_threshold_var.set(config.get('account_switch_threshold', DEFAULT_ACCOUNT_SWITCH_THRESHOLD))
                self.log_to_gui("Configuration loaded.", "INFO")
                self.update_gui_accounts_list_display() # Reflect loaded primary email
        except FileNotFoundError: self.log_to_gui("No config file. Using defaults.", "INFO")
        except json.JSONDecodeError: self.log_to_gui("Error decoding config. Using defaults.", "ERROR")
        except Exception as e: self.log_to_gui(f"Failed to load config: {e}", "ERROR")


# --- Main Application Entry Point ---
if __name__ == "__main__":
    check_prerequisites()
    main_logger = setup_logging(log_level=logging.INFO) # DEBUG for more verbosity
    main_logger.info("Application starting...")
    try:
        app = LinkedInCheckerGUI(app_logger=main_logger)
        app.mainloop()
    except Exception as e:
        main_logger.critical(f"Unhandled GUI exception: {e}", exc_info=True)
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Fatal Error", f"Critical error: {e}\nCheck logs.")
            root.destroy()
        except: print(f"FATAL APP ERROR: {e}") # Absolute fallback
    main_logger.info("Application finished.")
