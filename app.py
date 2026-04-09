from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv('API_KEY')
KMA_KEY = os.getenv('KMA_KEY')

from flask import Flask, render_template
import requests
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def index():
    #에어코리아 데이터
    url="http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": API_KEY,
        "stationName": "중구",
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 1,
        "returnType": "json",
        "ver": "1.0"

    }
    response = requests.get(url, params=params)
    data = response.json()
    item = data['response']['body']['items'][0]
    print(item)
    PM25 = float(item['pm25Value'])
    PM10 = float(item['pm10Value'])

    #기상청 데이터
    from datetime import datetime
    import pytz

    한국시간 = datetime.now(pytz.timezone('Asia/Seoul'))
    tm = 한국시간.strftime("%Y%m%d%H00")
    kma_url = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"
    kma_params = {"tm": tm, "stn": "108", "authKey": KMA_KEY}
    kma_response = requests.get(kma_url, params=kma_params)
    lines = kma_response.text.strip().split('\n')
    for line in lines:
        if '2026' in line and len(line.split()) > 13:
            kma_data = line.split()
            온도 = float(kma_data[11])
            습도 = float(kma_data[13])
            풍속 = float(kma_data[3])

    # 위험도 계산
    # 정규화
    PM25_n = min(PM25 / 75 * 100, 100)
    PM10_n = min(PM10 / 150 * 100, 100)
    습도_n = abs(습도 - 50) * 2
    풍속_n = max(0, (1 - 풍속 / 20) * 100)
    온도_n = min(max((온도 + 20) / 60 * 100, 0), 100)

    # 가중치 적용
    위험도 = (PM25_n * 0.35) + (PM10_n * 0.25) + (습도_n * 0.20) + (풍속_n * 0.15) + (온도_n * 0.05)
    위험도 = round(위험도, 1)

    if 위험도 >= 80:
        등급 = "매우 위험"
    elif 위험도 >= 60:
        등급 = "나쁨"
    elif 위험도 >= 40:
        등급 = "보통"
    else:
        등급 = "좋음"
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>미세먼지 위험도</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .card {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1 {{
            text-align: center;
            color: #333;
        }}
        .grade {{
            text-align: center;
            font-size: 48px;
            font-weight: bold;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            color: {'#2ecc71' if 등급 == '좋음' else '#f39c12' if 등급 == '보통' else '#e74c3c'};
        }}
        .data {{
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
        }}
        .data-item {{
            text-align: center;
        }}
        .data-item .value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .data-item .label {{
            font-size: 12px;
            color: #999;
        }}
        .score {{
            text-align: center;
            font-size: 18px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🌫️ 미세먼지 체감 위험도</h1>
        <div class="grade">{등급}</div>
        <div class="score">위험도 점수: {위험도}점</div>
        <div class="data">
            <div class="data-item">
                <div class="value">{PM25}</div>
                <div class="label">PM2.5</div>
            </div>
            <div class="data-item">
                <div class="value">{PM10}</div>
                <div class="label">PM10</div>
            </div>
            <div class="data-item">
                <div class="value">{온도}°C</div>
                <div class="label">온도</div>
            </div>
            <div class="data-item">
                <div class="value">{습도}%</div>
                <div class="label">습도</div>
            </div>
            <div class="data-item">
                <div class="value">{풍속}</div>
                <div class="label">풍속(m/s)</div>
            </div>
        </div>
    </div>
</body>
</html>
"""

if __name__ == '__main__':
    app.run(debug=True)
