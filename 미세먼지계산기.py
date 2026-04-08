import requests
from datetime import datetime

API_KEY= "03a15862d5fe0c62847dd26dfac66a2a4f1d3c8b2463a2165cde1f83ea06b03e"
KMA_KEY = "z1NZ07X0T-aTWdO19A_mig"

url="http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"

params={
    "serviceKey":API_KEY,
    "stationName": "중구",
    "dataTerm": "DAILY",
    "pageNo": 1,
    "numOfRows":1,
    "returnType": "json",
    "ver": "1.0"
}

response = requests.get(url,params=params)
data=response.json()
print(data)

item = data['response']['body']['items'][0]
PM25=float(item['pm25Value'])
PM10=float(item['pm10Value'])    

kma_url="https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"
tm = datetime.now().strftime("%Y%m%d%H00")
kma_params={
    "tm": tm,
    "stn": "108",
    "authKey":KMA_KEY
}
kma_response = requests.get(kma_url, params = kma_params)
lines = kma_response.text.strip().split('\n')
for line in lines:
    if '2026' in line and len(line.split())>13:
        kma_data = line.split()
        온도=float(kma_data[11])
        습도=float(kma_data[13])
        풍속=float(kma_data[3])
위험도=(PM25*0.35)+(PM10*0.25)+(습도*0.2)+(풍속*0.15)+(온도*0.05)

if 위험도>= 80: print("매우 위험 - 외출 금지")
elif 위험도>=60: print("나쁨 - 마스크착용")
elif 위험도>=40: print("보통 - 주의 필요")
else: print("좋음 - 외출 괜찮아요")
print("위험도 점수:", round(위험도,1))
print("PM2.5:",PM25, "/PM10:",PM10)
print("온도:",온도,"/습도:",습도,"/풍속:",풍속)