from urllib.request import urlopen
from bs4 import BeautifulSoup

def scrape_onion_servers():
    scrape_page = "https://1209k.com/bitcoin-eye/ele.php?chain=tbtc"
    print("Scraping URL:", scrape_page)
    page = urlopen(scrape_page)
    soup = BeautifulSoup(page, "html.parser")
    table_data = soup.find_all("td")

    servers = list()
    for i, td in enumerate(table_data):
        if ".onion" in td.text:
            servers.append((td.text, int(table_data[i+1].text)))
    return servers

def main():
    print(scrape_onion_servers())

if __name__ == "__main__":
    main()
