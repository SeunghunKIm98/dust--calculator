from dotenv import load_dotenv
import os
load_dotenv()

API_KEY = os.getenv('API_KEY')
KMA_KEY = os.getenv('KMA_KEY')

from flask import Flask, render_template, request
import requests
from datetime import datetime
import pytz

app = Flask(__name__)
app.jinja_env.globals.update(enumerate=enumerate)

# 서울 25개 측정소
STATIONS = [
    "종로구", "중구", "용산구", "성동구", "광진구",
    "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구",
    "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구"
]

# ─────────────────────────────────────────
# 계절 판별
# ─────────────────────────────────────────
def get_season():
    kst = pytz.timezone('Asia/Seoul')
    month = datetime.now(kst).month
    if month in [3, 4, 5]:   return 'spring'
    elif month in [6, 7, 8]: return 'summer'
    elif month in [9, 10, 11]: return 'fall'
    else: return 'winter'

SEASON_KR = {
    'spring': '봄', 'summer': '여름',
    'fall': '가을', 'winter': '겨울'
}
SEASON_MONTH = {
    'spring': '3~5월', 'summer': '6~8월',
    'fall': '9~11월', 'winter': '12~2월'
}

# ─────────────────────────────────────────
# 계절별 가중치 (조우싱 2014 Table 4.5~4.8)
# ─────────────────────────────────────────
SEASON_WEIGHTS = {
    'spring': (0.38, 0.22, 0.27, 0.08, 0.05),
    'summer': (0.38, 0.22, 0.17, 0.07, 0.16),
    'fall':   (0.38, 0.22, 0.13, 0.18, 0.09),
    'winter': (0.38, 0.22, 0.05, 0.17, 0.18),
}

# ─────────────────────────────────────────
# CAI 비선형 정규화 (환경부 공식)
# ─────────────────────────────────────────
def calc_cai_pm25(cp):
    breakpoints = [
        (0,  15,  0,   50),
        (16, 35,  51,  100),
        (36, 75,  101, 250),
        (76, 150, 251, 500),
    ]
    for bplo, bphi, ilo, ihi in breakpoints:
        if bplo <= cp <= bphi:
            return (ihi - ilo) / (bphi - bplo) * (cp - bplo) + ilo
    return 500

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

# ─────────────────────────────────────────
# 기상인자 정규화
# ─────────────────────────────────────────
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

# ─────────────────────────────────────────
# 위험도 계산
# ─────────────────────────────────────────
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

# ─────────────────────────────────────────
# 데이터 수집 함수
# ─────────────────────────────────────────
def get_air_data(station):
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": API_KEY,
        "stationName": station,
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 1,
        "returnType": "json",
        "ver": "1.0"
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data['response']['body']['items'][0]

def get_weather_data():
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

    # 값 못 가져왔을 때 기본값 설정
    if 온도 is None: 온도 = 15.0
    if 습도 is None: 습도 = 50.0
    if 풍속 is None: 풍속 = 2.0

    return 온도, 습도, 풍속, 한국시간
# ─────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────
@app.route('/')
def index():
    station = request.args.get('station', '중구')
    if station not in STATIONS:
        station = '중구'

    item = get_air_data(station)
    온도, 습도, 풍속, 한국시간 = get_weather_data()

    PM25 = float(item['pm25Value'])
    PM10 = float(item['pm10Value'])
    O3   = float(item.get('o3Value', 0))
    NO2  = float(item.get('no2Value', 0))
    CO   = float(item.get('coValue', 0))

    # 등급 가져오기
    grades = {
        'PM2.5':    item.get('pm25Grade', '-'),
        'PM10':     item.get('pm10Grade', '-'),
        'O3':       item.get('o3Grade', '-'),
        'NO2':      item.get('no2Grade', '-'),
        'CO':       item.get('coGrade', '-'),
    }

    grade_kr = {'1': '좋음', '2': '보통', '3': '나쁨', '4': '매우나쁨', '-': '-'}
    grade_order = {'1': 1, '2': 2, '3': 3, '4': 4, '-': 0}

    # TOP3 계산 (등급 나쁜 순서로 정렬)
    pollutant_list = [
        {'name': 'PM2.5', 'value': f'{PM25} µg/m³', 'grade': grades['PM2.5'],
         'grade_kr': grade_kr.get(grades['PM2.5'], '-'),
         'desc': '초미세먼지', 'order': grade_order.get(grades['PM2.5'], 0)},
        {'name': 'PM10',  'value': f'{PM10} µg/m³', 'grade': grades['PM10'],
         'grade_kr': grade_kr.get(grades['PM10'], '-'),
         'desc': '미세먼지', 'order': grade_order.get(grades['PM10'], 0)},
        {'name': 'O3',    'value': f'{O3} ppm',     'grade': grades['O3'],
         'grade_kr': grade_kr.get(grades['O3'], '-'),
         'desc': '오존', 'order': grade_order.get(grades['O3'], 0)},
        {'name': 'NO2',   'value': f'{NO2} ppm',    'grade': grades['NO2'],
         'grade_kr': grade_kr.get(grades['NO2'], '-'),
         'desc': '이산화질소', 'order': grade_order.get(grades['NO2'], 0)},
        {'name': 'CO',    'value': f'{CO} ppm',     'grade': grades['CO'],
         'grade_kr': grade_kr.get(grades['CO'], '-'),
         'desc': '일산화탄소', 'order': grade_order.get(grades['CO'], 0)},
    ]

    top3 = sorted(pollutant_list, key=lambda x: x['order'], reverse=True)[:3]

    # 한줄 요약 자동 생성
    worst = top3[0]
    if worst['grade'] == '4':
        summary = f"오늘 {station}은 {worst['desc']} 수치가 매우 나쁩니다. 외출을 자제하세요."
    elif worst['grade'] == '3':
        summary = f"오늘 {station}은 {worst['desc']} 영향이 큽니다. 마스크를 착용하세요."
    elif worst['grade'] == '2':
        summary = f"오늘 {station}은 전반적으로 보통 수준입니다. 민감군은 주의하세요."
    else:
        summary = f"오늘 {station}은 대기질이 좋습니다. 야외활동을 즐기세요! 😊"

    위험도, season, details = calc_risk(PM25, PM10, 풍속, 온도, 습도)

    return render_template('index.html',
        active_page='index',
        stations=STATIONS,
        current_station=station,
        top3=top3,
        summary=summary,
        위험도=위험도,
        now_str=한국시간.strftime("%Y년 %m월 %d일 %H시 기준")
    )

@app.route('/risk')
def risk():
    station = request.args.get('station', '중구')
    if station not in STATIONS:
        station = '중구'

    item = get_air_data(station)
    온도, 습도, 풍속, 한국시간 = get_weather_data()

    PM25 = float(item['pm25Value'])
    PM10 = float(item['pm10Value'])
    
    # 기본 등급
    pm25_grade = item.get('pm25Grade', '-')
    pm10_grade = item.get('pm10Grade', '-')
    o3_grade   = item.get('o3Grade', '-')
    no2_grade  = item.get('no2Grade', '-')
    co_grade   = item.get('coGrade', '-')

    위험도, season, details = calc_risk(PM25, PM10, 풍속, 온도, 습도)

    if 위험도 >= 80:   등급 = '매우 위험'
    elif 위험도 >= 60: 등급 = '나쁨'
    elif 위험도 >= 40: 등급 = '보통'
    else:              등급 = '좋음'

    return render_template('risk.html',
        active_page='risk',
        stations=STATIONS,
        current_station=station,
        PM25=PM25, PM10=PM10,
        온도=온도, 습도=습도, 풍속=풍속,
        위험도=위험도, 등급=등급,
        season=season, details=details,
        SEASON_KR=SEASON_KR, SEASON_MONTH=SEASON_MONTH,
        pm25_grade=pm25_grade, pm10_grade=pm10_grade,
        o3_grade=o3_grade, no2_grade=no2_grade, co_grade=co_grade,
        now_str=한국시간.strftime("%Y년 %m월 %d일 %H시 기준")
    )

@app.route('/today')
def today():
    station = request.args.get('station', '중구')
    pollutant = request.args.get('pollutant', 'PM2.5')
    if station not in STATIONS:
        station = '중구'

    # 24시간치 데이터 가져오기
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {
        "serviceKey": API_KEY,
        "stationName": station,
        "dataTerm": "DAILY",
        "pageNo": 1,
        "numOfRows": 24,
        "returnType": "json",
        "ver": "1.0"
    }
    response = requests.get(url, params=params)
    data = response.json()
    items = data['response']['body']['items']

    # 오염물질별 정보
    POLLUTANT_INFO = {
    'PM2.5': {
        'name': 'PM2.5', 'desc': '초미세먼지',
        'unit': 'µg/m³', 'value_key': 'pm25Value', 'grade_key': 'pm25Grade',
        'criteria': [
            {'grade': '1', 'label': '좋음',     'range': '0 ~ 15 µg/m³',  'emoji': '🟢'},
            {'grade': '2', 'label': '보통',     'range': '16 ~ 35 µg/m³', 'emoji': '🟡'},
            {'grade': '3', 'label': '나쁨',     'range': '36 ~ 75 µg/m³', 'emoji': '🟠'},
            {'grade': '4', 'label': '매우나쁨', 'range': '76 µg/m³ ~',    'emoji': '🔴'},
        ]
    },
    'PM10': {
        'name': 'PM10', 'desc': '미세먼지',
        'unit': 'µg/m³', 'value_key': 'pm10Value', 'grade_key': 'pm10Grade',
        'criteria': [
            {'grade': '1', 'label': '좋음',     'range': '0 ~ 30 µg/m³',   'emoji': '🟢'},
            {'grade': '2', 'label': '보통',     'range': '31 ~ 80 µg/m³',  'emoji': '🟡'},
            {'grade': '3', 'label': '나쁨',     'range': '81 ~ 150 µg/m³', 'emoji': '🟠'},
            {'grade': '4', 'label': '매우나쁨', 'range': '151 µg/m³ ~',    'emoji': '🔴'},
        ]
    },
    'O3': {
        'name': 'O3', 'desc': '오존',
        'unit': 'ppm', 'value_key': 'o3Value', 'grade_key': 'o3Grade',
        'criteria': [
            {'grade': '1', 'label': '좋음',     'range': '0 ~ 0.03 ppm',    'emoji': '🟢'},
            {'grade': '2', 'label': '보통',     'range': '0.04 ~ 0.09 ppm', 'emoji': '🟡'},
            {'grade': '3', 'label': '나쁨',     'range': '0.1 ~ 0.15 ppm',  'emoji': '🟠'},
            {'grade': '4', 'label': '매우나쁨', 'range': '0.16 ppm ~',      'emoji': '🔴'},
        ]
    },
    'NO2': {
        'name': 'NO2', 'desc': '이산화질소',
        'unit': 'ppm', 'value_key': 'no2Value', 'grade_key': 'no2Grade',
        'criteria': [
            {'grade': '1', 'label': '좋음',     'range': '0 ~ 0.03 ppm',    'emoji': '🟢'},
            {'grade': '2', 'label': '보통',     'range': '0.04 ~ 0.09 ppm', 'emoji': '🟡'},
            {'grade': '3', 'label': '나쁨',     'range': '0.1 ~ 0.15 ppm',  'emoji': '🟠'},
            {'grade': '4', 'label': '매우나쁨', 'range': '0.16 ppm ~',      'emoji': '🔴'},
        ]
    },
    'CO': {
        'name': 'CO', 'desc': '일산화탄소',
        'unit': 'ppm', 'value_key': 'coValue', 'grade_key': 'coGrade',
        'criteria': [
            {'grade': '1', 'label': '좋음',     'range': '0 ~ 2 ppm',  'emoji': '🟢'},
            {'grade': '2', 'label': '보통',     'range': '3 ~ 9 ppm',  'emoji': '🟡'},
            {'grade': '3', 'label': '나쁨',     'range': '10 ~ 15 ppm','emoji': '🟠'},
            {'grade': '4', 'label': '매우나쁨', 'range': '16 ppm ~',   'emoji': '🔴'},
        ]
    },
}

    info = POLLUTANT_INFO.get(pollutant, POLLUTANT_INFO['PM2.5'])

    # 24시간 그래프용 데이터
    chart_labels = []
    chart_values = []
    for item in reversed(items):
        try:
            val = float(item.get(info['value_key'], 0) or 0)
            time_str = item.get('dataTime', '')
            hour = time_str[-5:]  # "14:00" 형태
            chart_labels.append(hour)
            chart_values.append(val)
        except:
            pass

    # 현재 수치 (가장 최신)
    latest = items[0]
    current_value = latest.get(info['value_key'], '-')
    current_grade = latest.get(info['grade_key'], '-')
    grade_kr = {'1': '좋음', '2': '보통', '3': '나쁨', '4': '매우나쁨', '-': '-'}

    _, _, _, 한국시간 = get_weather_data()

    return render_template('today.html',
        active_page='today',
        stations=STATIONS,
        current_station=station,
        pollutant=pollutant,
        info=info,
        current_value=current_value,
        current_grade=current_grade,
        current_grade_kr=grade_kr.get(current_grade, '-'),
        chart_labels=chart_labels,
        chart_values=chart_values,
        now_str=한국시간.strftime("%Y년 %m월 %d일 %H시 기준")
    )

@app.route('/pollutants')
def pollutants():
    station = request.args.get('station', '중구')
    return render_template('pollutants.html',
        active_page='pollutants',
        stations=STATIONS,
        current_station=station
    )

@app.route('/guide')
def guide():
    return render_template('guide.html',
        active_page='guide',
        stations=STATIONS,
        current_station='중구'
    )

@app.route('/about')
def about():
    return render_template('about.html',
        active_page='about',
        stations=STATIONS,
        current_station='중구'
    )

if __name__ == '__main__':
    app.run(debug=True)