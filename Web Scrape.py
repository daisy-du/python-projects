
import pandas as pd 
import os 
import multiprocessing
import requests as r
from bs4 import BeautifulSoup as bs

data = pd.read_csv('UW_capstone.csv')

data = data[['TITLE', 'APPLICATION_URL', 'STORE_ID']]
data = data.drop_duplicates()
data.reset_index(drop=True, inplace=True)
data = data.tail(len(data) - 21616)
data.reset_index(drop=True, inplace=True)

data0 = data.iloc[21000:21300,:]
data1 = data.iloc[21300:21600,:]
data2 = data.iloc[21600:21900,:]
data3 = data.iloc[21900:22141,:]

results = []

def scrape(url, df, title):
    page = r.get(url)
    soup = bs(page.content, 'html.parser')
    if (str(soup.find('div', class_='BHMmbe')) != 'None'):
        genre = soup.find_all('span', class_='T32cc UAO9ie')
        rating = soup.find('div', class_='BHMmbe').text
        ratinglabel = soup.find('span', class_='EymY4b')
        total_rating = ratinglabel.findChildren('span')[1].text
        installs = soup.find_all('div', class_='hAyfc')[2].text.replace('Installs', '')
        if (installs[-1] != '+'):
            installs = soup.find_all('div', class_='hAyfc')[3].text.replace('Installs', '')
        review = str(soup.find('div', jsname='sngebd').get_text('\n')).replace('\n', ' ')
        #print(genre[1].text + " " + rating + " " + total_rating + " " + installs + '\n' + review)
        df = df.append({'App Title':title, 
                    'Category':genre[1].text, 'Rating':rating, 
                    'Number of Rating':total_rating, 
                    'Installs':installs, 
                    'Description':review}, ignore_index=True)
        print(title)
    return df

def scrape_df(dataframe):
    new_df = pd.DataFrame()
    process_id = os.getpid()
    print(f'Process ID: {process_id}')
    for i, j in dataframe.iterrows(): 
        print(i)
        new_df = scrape(j.APPLICATION_URL, new_df, j.TITLE)
    return new_df.values.tolist()

def collect_results(result):
    """Uses apply_async's callback to setup up a separate Queue for each process"""
    results.extend(result)

pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
dataframes = [data0, data1,data2,data3]

for dataframe in dataframes: 
    pool.apply_async(scrape_df, args=(dataframe, ), callback=collect_results)
pool.close()
pool.join()

results = pd.DataFrame(results)

results.to_csv('results9.csv')

