from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv('API_KEY')
KMA_KEY = os.getenv('KMA_KEY')

from flask import Flask, request
import requests
from datetime import datetime
import pytz

app = Flask(__name__)

# 계절판별
def get_season():
    kst = pytz.timezone('Asia/Seoul')
    month = datetime.now(kst).month
    if month in [3, 4, 5]:
        return 'spring'
    elif month in [6, 7, 8]:
        return 'summer'
    elif month in [9, 10, 11]:
        return 'fall'
    else:
        return 'winter'

SEASON_KR = {
    'spring': '봄',
    'summer': '여름',
    'fall':   '가을',
    'winter': '겨울',
}
SEASON_MONTH = {
    'spring': '3~5월',
    'summer': '6~8월',
    'fall':   '9~11월',
    'winter': '12~2월',
}

# 계절별 가중치
# 출처: 조우싱(2014) Table 4.5~4.8
# PM2.5 기상인자 상관계수 절대값 비율로 산출
SEASON_WEIGHTS = {
    #        pm25   pm10   wind   temp   humid
    'spring': (0.38, 0.22, 0.27, 0.08, 0.05),
    'summer': (0.38, 0.22, 0.17, 0.07, 0.16),
    'fall':   (0.38, 0.22, 0.13, 0.18, 0.09),
    'winter': (0.38, 0.22, 0.05, 0.17, 0.18),
}

#CAI 비선형 정규화(환경부 공식)
# Ip = (IHI - ILO) / (BPHI - BPLO) × (Cp - BPLO) + ILO

def calc_cai_pm25(cp):
    breakpoints = [
        # (농도 하한, 농도 상한, CAI 하한, CAI 상한)
        (0,  15,  0,   50),   # 좋음 구간
        (16, 35,  51,  100),  # 보통 구간
        (36, 75,  101, 250),  # 나쁨 구간
        (76, 150, 251, 500),  # 매우나쁨 구간
    ]
    for bplo, bphi, ilo, ihi in breakpoints:
        if bplo <= cp <= bphi:
            return (ihi - ilo) / (bphi - bplo) * (cp - bplo) + ilo
    return 500  # 150 초과시

def calc_cai_pm10(cp):
    breakpoints = [
        (0,  30,  0,   50),
        (31, 80,  51,  100),
        (81, 150, 101, 250),
        (151,300, 251, 500),
    ]
    for bplo, bphi, ilo, ihi in breakpoints:
        if bplo <= cp <= bphi:
            return (ihi - ilo) / (bphi - bplo) * (cp - bplo) + ilo
    return 500        

#기상인자 정규화(계절별 방향 반영)

def normalize_wind(wind):
    return max(0, min(100, (1 - wind / 10) * 100))

def normalize_temp(temp, season):
    base = (temp + 15) / 50 * 100
    if season == 'winter':
        return max(0, min(100, base))
    else:
        return max(0, min(100, 100 - base))

def normalize_humid(humid, season):
    if season == 'winter':
        return max(0, min(100, humid))
    else:
        return max(0, min(100, abs(humid - 50) * 2))
    
# 위험도 계산
def calc_risk(pm25, pm10, wind, temp, humid):
    season = get_season()
    w_pm25, w_pm10, w_wind, w_temp, w_humid = SEASON_WEIGHTS[season]

    s_pm25  = calc_cai_pm25(pm25) / 5
    s_pm10  = calc_cai_pm10(pm10) / 5
    s_wind  = normalize_wind(wind)
    s_temp  = normalize_temp(temp, season)
    s_humid = normalize_humid(humid, season)

    score = (
        s_pm25  * w_pm25  +
        s_pm10  * w_pm10  +
        s_wind  * w_wind  +
        s_temp  * w_temp  +
        s_humid * w_humid
    )
    return round(score, 1), season, {
        'pm25':  {'score': round(s_pm25, 1),  'weight': int(w_pm25 * 100)},
        'pm10':  {'score': round(s_pm10, 1),  'weight': int(w_pm10 * 100)},
        'wind':  {'score': round(s_wind, 1),  'weight': int(w_wind * 100)},
        'temp':  {'score': round(s_temp, 1),  'weight': int(w_temp * 100)},
        'humid': {'score': round(s_humid, 1), 'weight': int(w_humid * 100)},
    }

# 서울 25개 측정소 목록
STATIONS = [
    "종로구", "중구", "용산구", "성동구", "광진구",
    "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구",
    "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구"
]

@app.route('/')
def index():
    # 사용자가 선택한 측정소 (없으면 기본값 중구)
    station = request.args.get('station', '중구')

    # 선택한 측정소가 목록에 없으면 중구로 강제
    if station not in STATIONS:
        station = '중구'

    # 에어코리아 데이터
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": API_KEY,
        "stationName": station,   # ← 여기만 바뀜!
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 1,
        "returnType": "json",
        "ver": "1.0"
    }
    response = requests.get(url, params=params)
    data = response.json()
    item = data['response']['body']['items'][0]
    PM25 = float(item['pm25Value'])
    PM10 = float(item['pm10Value'])

    # 기상청 데이터 (기존 그대로)
    kst = pytz.timezone('Asia/Seoul')
    한국시간 = datetime.now(kst)
    tm = 한국시간.strftime("%Y%m%d%H00")
    kma_url = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"
    kma_params = {"tm": tm, "stn": "108", "authKey": KMA_KEY}
    kma_response = requests.get(kma_url, params=kma_params)
    lines = kma_response.text.strip().split('\n')
    온도 = 습도 = 풍속 = None
    for line in lines:
        year = str(한국시간.year)
        if year in line and len(line.split()) > 13:
            kma_data = line.split()
            온도 = float(kma_data[11])
            습도 = float(kma_data[13])
            풍속 = float(kma_data[3])

    위험도, season, details = calc_risk(PM25, PM10, 풍속, 온도, 습도)

    grade_map = {
        '매우 위험': ('#c0392b', '😷', '외출 금지'),
        '나쁨':     ('#e67e22', '😰', '마스크 착용'),
        '보통':     ('#f1c40f', '😐', '주의 필요'),
        '좋음':     ('#27ae60', '😊', '외출 괜찮아요'),
    }
    if 위험도 >= 80:
        등급 = '매우 위험'
    elif 위험도 >= 60:
        등급 = '나쁨'
    elif 위험도 >= 40:
        등급 = '보통'
    else:
        등급 = '좋음'

    color, emoji, advice = grade_map[등급]
    now_str = 한국시간.strftime("%Y년 %m월 %d일 %H시 기준")

    season_note = {
        'spring': '봄철: 풍속 영향 가장 큼 (황사 시즌)',
        'summer': '여름철: 습도·강수 영향 반영',
        'fall':   '가을철: 기온 영향 가장 큼',
        'winter': '겨울철: 습도·기온 방향 반전 (역전층 효과)',
    }

    # 드롭다운 옵션 HTML 생성
    station_options = ""
    for s in STATIONS:
        selected = "selected" if s == station else ""
        station_options += f'<option value="{s}" {selected}>{s}</option>\n'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>미세먼지 체감 위험도</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Apple SD Gothic Neo', Arial, sans-serif;
            background: #eef2f7;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: white;
            border-radius: 20px;
            padding: 36px 32px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 8px 24px rgba(0,0,0,0.10);
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 20px;
            color: #333;
            margin-bottom: 4px;
        }}
        .header .time {{
            font-size: 12px;
            color: #aaa;
        }}
        /* 측정소 선택 드롭다운 */
        .station-select {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin-bottom: 20px;
        }}
        .station-select label {{
            font-size: 13px;
            color: #666;
        }}
        .station-select select {{
            padding: 6px 12px;
            border-radius: 20px;
            border: 1px solid #ddd;
            font-size: 13px;
            color: #333;
            background: #f8f9fb;
            cursor: pointer;
            outline: none;
        }}
        .station-select select:focus {{
            border-color: #4a6cf7;
        }}
        .grade-box {{
            background: {color}18;
            border: 2px solid {color};
            border-radius: 16px;
            text-align: center;
            padding: 24px 16px;
            margin-bottom: 20px;
        }}
        .grade-box .emoji {{ font-size: 52px; }}
        .grade-box .grade-text {{
            font-size: 32px;
            font-weight: 800;
            color: {color};
            margin: 8px 0 4px;
        }}
        .grade-box .advice {{
            font-size: 15px;
            color: #555;
        }}
        .score-row {{
            display: flex;
            justify-content: center;
            align-items: baseline;
            gap: 6px;
            margin-bottom: 24px;
        }}
        .score-row .num {{
            font-size: 42px;
            font-weight: 700;
            color: {color};
        }}
        .score-row .unit {{
            font-size: 16px;
            color: #888;
        }}
        .measures {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 8px;
            margin-bottom: 24px;
        }}
        .measure-item {{
            background: #f8f9fb;
            border-radius: 10px;
            padding: 10px 4px;
            text-align: center;
        }}
        .measure-item .val {{
            font-size: 16px;
            font-weight: 700;
            color: #333;
        }}
        .measure-item .lbl {{
            font-size: 10px;
            color: #999;
            margin-top: 2px;
        }}
        .weights-section {{ margin-bottom: 20px; }}
        .weights-section .section-title {{
            font-size: 12px;
            color: #888;
            margin-bottom: 10px;
            font-weight: 600;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .weight-row {{
            display: flex;
            align-items: center;
            margin-bottom: 8px;
            gap: 8px;
        }}
        .weight-row .name {{
            font-size: 12px;
            color: #555;
            width: 52px;
            flex-shrink: 0;
        }}
        .weight-row .bar-wrap {{
            flex: 1;
            background: #eee;
            border-radius: 4px;
            height: 8px;
            overflow: hidden;
        }}
        .weight-row .bar {{
            height: 100%;
            border-radius: 4px;
            background: {color};
            opacity: 0.75;
        }}
        .weight-row .pct {{
            font-size: 11px;
            color: #888;
            width: 28px;
            text-align: right;
            flex-shrink: 0;
        }}
        .weight-row .sc {{
            font-size: 11px;
            color: #aaa;
            width: 38px;
            text-align: right;
            flex-shrink: 0;
        }}
        .season-badge {{
            display: inline-block;
            background: #f0f4ff;
            color: #4a6cf7;
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 6px;
        }}
        .season-note {{
            font-size: 11px;
            color: #aaa;
            margin-bottom: 20px;
        }}
        .footer {{
            text-align: center;
            font-size: 10px;
            color: #ccc;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
<div class="card">
    <div class="header">
        <h1>🌫️ 미세먼지 체감 위험도</h1>
        <div class="time">{now_str}</div>
    </div>

    <!-- 측정소 선택 드롭다운 -->
    <div class="station-select">
        <label>📍 측정소</label>
        <select onchange="location.href='/?station='+this.value">
            {station_options}
        </select>
    </div>

    <div class="grade-box">
        <div class="emoji">{emoji}</div>
        <div class="grade-text">{등급}</div>
        <div class="advice">{advice}</div>
    </div>

    <div class="score-row">
        <div class="num">{위험도}</div>
        <div class="unit">/ 100점</div>
    </div>

    <div class="measures">
        <div class="measure-item">
            <div class="val">{PM25}</div>
            <div class="lbl">PM2.5</div>
        </div>
        <div class="measure-item">
            <div class="val">{PM10}</div>
            <div class="lbl">PM10</div>
        </div>
        <div class="measure-item">
            <div class="val">{온도}°</div>
            <div class="lbl">온도(℃)</div>
        </div>
        <div class="measure-item">
            <div class="val">{습도}%</div>
            <div class="lbl">습도</div>
        </div>
        <div class="measure-item">
            <div class="val">{풍속}</div>
            <div class="lbl">풍속(m/s)</div>
        </div>
    </div>

    <div class="season-badge">
        {SEASON_KR[season]} ({SEASON_MONTH[season]}) 가중치 적용 중
    </div>
    <div class="season-note">{season_note[season]}</div>

    <div class="weights-section">
        <div class="section-title">인자별 기여도</div>
        <div class="weight-row">
            <div class="name">PM2.5</div>
            <div class="bar-wrap"><div class="bar" style="width:{details['pm25']['weight']}%"></div></div>
            <div class="pct">{details['pm25']['weight']}%</div>
            <div class="sc">{details['pm25']['score']}점</div>
        </div>
        <div class="weight-row">
            <div class="name">PM10</div>
            <div class="bar-wrap"><div class="bar" style="width:{details['pm10']['weight']}%"></div></div>
            <div class="pct">{details['pm10']['weight']}%</div>
            <div class="sc">{details['pm10']['score']}점</div>
        </div>
        <div class="weight-row">
            <div class="name">풍속</div>
            <div class="bar-wrap"><div class="bar" style="width:{details['wind']['weight']}%"></div></div>
            <div class="pct">{details['wind']['weight']}%</div>
            <div class="sc">{details['wind']['score']}점</div>
        </div>
        <div class="weight-row">
            <div class="name">온도</div>
            <div class="bar-wrap"><div class="bar" style="width:{details['temp']['weight']}%"></div></div>
            <div class="pct">{details['temp']['weight']}%</div>
            <div class="sc">{details['temp']['score']}점</div>
        </div>
        <div class="weight-row">
            <div class="name">습도</div>
            <div class="bar-wrap"><div class="bar" style="width:{details['humid']['weight']}%"></div></div>
            <div class="pct">{details['humid']['weight']}%</div>
            <div class="sc">{details['humid']['score']}점</div>
        </div>
    </div>

    <div class="footer">
        PM 정규화: 환경부 CAI 비선형 공식<br>
        가중치 출처: 조우싱(2014) 서울시 기상인자-PM2.5 계절별 피어슨 상관계수 (Table 4.5~4.8)
    </div>
</div>
</body>
</html>"""

if __name__ == '__main__':
    app.run(debug=True)