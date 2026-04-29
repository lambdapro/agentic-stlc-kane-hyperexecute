from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class ProductsPage:  # Renamed from CreditCardsPage
    URL = "https://ecommerce-playground.lambdatest.io/"
    SHOP_NAV = (By.XPATH, "//a[contains(., 'Shop')] | //span[contains(., 'Category')]")
    PRODUCT_TILES = (By.CSS_SELECTOR, ".product-layout, [class*='card-tile'], [class*='CardTile'], [data-testid*='card']")
    FILTER_CHIPS = (By.CSS_SELECTOR, ".list-group-item, [class*='filter-chip'], [role='tab']")
    VIEW_DETAILS_LINKS = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'view detail') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'learn more') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'add to cart')]")
    PRODUCT_DETAILS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'price') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'description') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'stock')]")
    LOGIN_BUTTON = (By.XPATH, "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'log in') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'sign in')]")
    PRODUCT_HIGHLIGHTS = (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'featured product') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'highlight')]")
    COOKIE_BANNER_ACCEPT = (
        By.XPATH,
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]"
        "|//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'agree')]"
        "|//button[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept')]",
    )
    LOGIN_GATE = (
        By.XPATH,
        "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'log in to continue')]"
        "|//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'sign in to continue')]",
    )
    SEARCH_INPUT = (By.NAME, "search")
    SEARCH_BUTTON = (By.XPATH, "//button[contains(@class, 'btn-light') and contains(., 'Search')]")

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)

    def open(self):
        self.driver.get(self.URL)

    def wait_for_ready_state(self):
        self.wait.until(lambda current_driver: current_driver.execute_script("return document.readyState") == "complete")

    def dismiss_common_overlays(self):
        try:
            buttons = self.driver.find_elements(*self.COOKIE_BANNER_ACCEPT)
            for button in buttons[:2]:
                if button.is_displayed():
                    self.safe_click(button)
                    break
        except Exception:
            pass

    def scroll_to_element(self, element):
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
            element,
        )

    def safe_click(self, element):
        self.scroll_to_element(element)
        try:
            self.wait.until(lambda _: element.is_displayed() and element.is_enabled())
            element.click()
            return True
        except (ElementClickInterceptedException, StaleElementReferenceException):
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False
        except Exception:
            try:
                self.driver.execute_script("arguments[0].click();", element)
                return True
            except Exception:
                return False

    def navigate_to_products_page(self):
        self.open()
        self.wait_for_ready_state()
        self.dismiss_common_overlays()
        try:
            shop_link = self.wait.until(EC.element_to_be_clickable(self.SHOP_NAV))
            self.safe_click(shop_link)
        except Exception:
            self.driver.get("https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path=57")
        self.wait_for_ready_state()
        self.dismiss_common_overlays()

    def get_product_tiles(self):
        return self.driver.find_elements(*self.PRODUCT_TILES)

    def get_filter_chips(self):
        return self.driver.find_elements(*self.FILTER_CHIPS)

    def apply_filter(self, filter_name: str):
        chips = self.get_filter_chips()
        for chip in chips:
            if filter_name.lower() in chip.text.lower():
                previous_url = self.current_url()
                previous_count = len(self.get_product_tiles())
                if not self.safe_click(chip):
                    continue
                self.wait.until(
                    lambda current_driver: current_driver.current_url != previous_url or len(self.get_product_tiles()) > 0
                )
                return len(self.get_product_tiles()) > 0 or previous_count > 0
        return False

    def click_first_product_details(self):
        links = self.driver.find_elements(*self.VIEW_DETAILS_LINKS)
        if links:
            return self.safe_click(links[0])
        tiles = self.get_product_tiles()
        if tiles:
            return self.safe_click(tiles[0])
        return False

    def get_product_details_elements(self):
        return self.driver.find_elements(*self.PRODUCT_DETAILS)

    def is_login_button_visible(self):
        elements = self.driver.find_elements(*self.LOGIN_BUTTON)
        return len(elements) > 0

    def is_login_gate_present(self):
        return len(self.driver.find_elements(*self.LOGIN_GATE)) > 0

    def get_product_highlights(self):
        return self.driver.find_elements(*self.PRODUCT_HIGHLIGHTS)

    def has_guest_browsing_content(self):
        return bool(self.get_product_highlights() or self.get_product_tiles())

    def current_url(self):
        return self.driver.current_url

    def page_title(self):
        return self.driver.title

    def search_for_product(self, product_name: str):
        search_input = self.wait.until(EC.visibility_of_element_located(self.SEARCH_INPUT))
        search_input.send_keys(product_name)
        search_button = self.wait.until(EC.element_to_be_clickable(self.SEARCH_BUTTON))
        self.safe_click(search_button)
        self.wait_for_ready_state()

    def get_search_results(self):
        return self.driver.find_elements(*self.PRODUCT_TILES)

    def add_first_product_to_cart(self):
        add_to_cart_button = (By.XPATH, "(//button[contains(@onclick, 'cart.add')])[1]")
        button = self.wait.until(EC.element_to_be_clickable(add_to_cart_button))
        return self.safe_click(button)

    def get_cart_total_text(self):
        cart_total = (By.ID, "cart-total")
        return self.wait.until(EC.visibility_of_element_located(cart_total)).text

    def navigate_to_cart(self):
        cart_button = (By.XPATH, "//a[@title='Shopping Cart']")
        button = self.wait.until(EC.element_to_be_clickable(cart_button))
        self.safe_click(button)
        self.wait_for_ready_state()

    def get_cart_products(self):
        cart_product_rows = (By.XPATH, "//table[@class='table table-bordered']//tbody//tr")
        return self.driver.find_elements(*cart_product_rows)

    def update_cart_quantity(self, product_name: str, quantity: int):
        product_row = (By.XPATH, f"//td/a[contains(text(), '{product_name}')]/ancestor::tr")
        quantity_input = (By.XPATH, f"//td/a[contains(text(), '{product_name}')]/ancestor::tr//input[@type='text']")
        update_button = (By.XPATH, f"//td/a[contains(text(), '{product_name}')]/ancestor::tr//button[@data-original-title='Update']")

        input_element = self.wait.until(EC.visibility_of_element_located(quantity_input))
        input_element.clear()
        input_element.send_keys(str(quantity))

        button_element = self.wait.until(EC.element_to_be_clickable(update_button))
        self.safe_click(button_element)
        self.wait_for_ready_state()
