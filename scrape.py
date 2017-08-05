from urllib.request import urlopen
from bs4 import BeautifulSoup

def scrape_onion_servers(chain_1209k="tbtc",
        scrape_page="https://1209k.com/bitcoin-eye/ele.php?chain={}"):
    url = scrape_page.format(chain_1209k)
    print("Scraping URL:", url)
    
    page = urlopen(url)
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
