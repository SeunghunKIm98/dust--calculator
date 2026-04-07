try:
    PM25=float(input("PM2.5 수치를 입력하세요: "))
    PM10=float(input("PM10 수치를 입력하세요: "))
    습도=float(input("습도를 입력하세요: "))
    풍속=float(input("습도를 입력하세요: "))
    온도=float(input("온도를 입력하세요: "))
    위험도=(PM25*0.35)+(PM10*0.25)+(습도*0.2)+(풍속*0.15)+(온도*0.05)
    if 위험도>= 80: print("매우 위험 - 외출 금지")
    elif 위험도>=60: print("나쁨 - 마스크착용")
    elif 위험도>=40: print("보통 - 주의 필요")
    else: print("좋음 - 외출 괜찮아요")
    print("위험도 점수:", round(위험도,1))
except:
    print("올바른 숫자를 입력해주세요!")