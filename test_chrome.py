from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

driver = webdriver.Chrome(ChromeDriverManager().install())
print("Chrome 驅動版本：", driver.capabilities['chrome']['chromedriverVersion'])
driver.quit()