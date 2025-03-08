import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QTextEdit
from PyQt5.QtCore import QTimer
import time
from binance.client import Client
import telegram
from datetime import datetime, timedelta
import logging
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.dates import DateFormatter
import numpy as np

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Binance API 키 설정
BINANCE_API_KEY = "L8ry25nFEi8WlusCGdE3HiX1pwUKsLqPu6y9rIEzI1lJoIZW8fDxIkvSAYM5PUq5"
BINANCE_API_SECRET = "cqkuNiuNptQQPtjeq4xjvfn89YOt5wd4zlDbEDeboizoUY1BihQUGIqrMafWdX8E"

# 텔레그램 봇 설정
TELEGRAM_BOT_TOKEN = "7090299071:AAHIfRWtwTYUUcBWP8b5jbpgvSvYkxZvWTk"
TELEGRAM_CHAT_ID = "7762299928"

class BitcoinMonitorGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bitcoin Price Monitor")
        self.setGeometry(100, 100, 1200, 800)
        
        # 메인 위젯 설정
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        
        # 차트 설정
        self.fig = Figure(figsize=(12, 6))
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)
        
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title('Bitcoin Price Chart (Last 30 minutes)')
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Price (USDT)')
        self.ax.grid(True)
        
        # 현재 가격 표시 라벨
        self.price_label = QLabel("Current Price: $0.00")
        self.price_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.price_label)
        
        # 누적 하락 금액 표시 라벨 추가
        self.drop_label = QLabel("30분 누적 하락: $0.00")
        self.drop_label.setStyleSheet("font-size: 14px; color: red;")
        layout.addWidget(self.drop_label)
        
        # 모니터링 시작 시간 표시 라벨 추가
        self.monitor_start_label = QLabel("모니터링 시작: -")
        self.monitor_start_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.monitor_start_label)
        
        # 로그 표시 영역
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)
        
        # 시작/정지 버튼
        self.start_stop_button = QPushButton("Stop Monitoring")
        self.start_stop_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.start_stop_button)
        
        # 데이터 저장용 변수들
        self.times = []
        self.prices = []
        self.price_history = []
        self.monitoring = True
        
        # 캔들 데이터 저장용 변수 추가
        self.candle_data = []  # (시가, 고가, 저가, 종가, 시간) 튜플 리스트
        self.last_candle_time = None
        
        # 매수 조건 모니터링 변수 추가
        self.monitoring_buy_conditions = False
        self.buy_monitoring_start_time = None
        self.buy_monitoring_end_time = None
        
        # Binance 클라이언트 및 텔레그램 봇 초기화
        self.binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        
        # 타이머 설정 (1분 간격)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(60000)  # 60000ms = 1분
        
        # 초기 데이터 업데이트
        self.update_data()

    def toggle_monitoring(self):
        self.monitoring = not self.monitoring
        if self.monitoring:
            self.start_stop_button.setText("Stop Monitoring")
            self.timer.start()
            self.log_message("모니터링을 시작합니다.")
        else:
            self.start_stop_button.setText("Start Monitoring")
            self.timer.stop()
            self.log_message("모니터링을 중지합니다.")

    def get_current_price(self):
        try:
            ticker = self.binance_client.get_symbol_ticker(symbol="BTCUSDT")
            return float(ticker['price'])
        except Exception as e:
            self.log_message(f"가격 조회 중 오류 발생: {e}")
            return None

    def send_telegram_message(self, message):
        try:
            self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            self.log_message("텔레그램 메시지 전송 완료")
        except Exception as e:
            self.log_message(f"텔레그램 메시지 전송 중 오류 발생: {e}")

    def log_message(self, message):
        current_time = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{current_time}] {message}")

    def update_candle_data(self, current_time, current_price):
        """5분 캔들 데이터 업데이트"""
        current_minute = current_time.minute
        current_5min = (current_minute // 5) * 5
        candle_start_time = current_time.replace(minute=current_5min, second=0, microsecond=0)
        
        if not self.candle_data or candle_start_time != self.last_candle_time:
            # 새로운 캔들 시작
            self.candle_data.append([current_price, current_price, current_price, current_price, candle_start_time])
            self.last_candle_time = candle_start_time
        else:
            # 현재 캔들 업데이트
            current_candle = self.candle_data[-1]
            current_candle[1] = max(current_candle[1], current_price)  # 고가
            current_candle[2] = min(current_candle[2], current_price)  # 저가
            current_candle[3] = current_price  # 종가
        
        # 30분 이전 데이터 제거
        self.candle_data = [x for x in self.candle_data 
                           if x[4] > current_time - timedelta(minutes=30)]

    def check_buy_conditions(self):
        """매수 진입 조건 체크"""
        if len(self.candle_data) < 3:  # 최소 3개의 캔들이 필요
            return False, "데이터 부족"
            
        last_three_candles = self.candle_data[-3:]
        
        # 1. 캔들의 길이가 점점 짧아지는지 체크
        candle_lengths = [abs(candle[3] - candle[0]) for candle in last_three_candles]
        decreasing_length = all(candle_lengths[i] > candle_lengths[i+1] for i in range(len(candle_lengths)-1))
        
        # 2. 이전 캔들과 현재 캔들의 종가 비교
        last_close = last_three_candles[-2][3]
        current_close = last_three_candles[-1][3]
        price_stabilizing = abs(current_close - last_close) < 100 or current_close > last_close
        
        # 3. 아래꼬리 체크 (캔들 하단 부분이 전체 캔들 길이의 30% 이상)
        current_candle = last_three_candles[-1]
        total_length = current_candle[1] - current_candle[2]  # 고가 - 저가
        if total_length > 0:
            lower_tail = current_candle[3] - current_candle[2]  # 종가 - 저가
            has_lower_tail = (lower_tail / total_length) >= 0.3
        else:
            has_lower_tail = False
            
        conditions_met = decreasing_length and price_stabilizing and has_lower_tail
        
        message = (
            "매수 진입 조건 분석:\n"
            f"1. 캔들 길이 감소: {'✅' if decreasing_length else '❌'}\n"
            f"2. 가격 안정화: {'✅' if price_stabilizing else '❌'}\n"
            f"3. 아래꼬리 형성: {'✅' if has_lower_tail else '❌'}"
        )
        
        return conditions_met, message

    def check_price_drop(self, current_time, current_price):
        self.price_history.append((current_time, current_price))
        self.price_history = [x for x in self.price_history 
                            if x[0] > current_time - timedelta(minutes=30)]
        
        # 캔들 데이터 업데이트
        self.update_candle_data(current_time, current_price)
        
        if len(self.price_history) > 1:
            oldest_price = self.price_history[0][1]
            price_drop = oldest_price - current_price
            
            # 누적 하락 금액 업데이트
            self.drop_label.setText(f"30분 누적 하락: ${price_drop:,.2f}")
            if price_drop > 0:
                self.drop_label.setStyleSheet("font-size: 14px; color: red;")
            else:
                self.drop_label.setStyleSheet("font-size: 14px; color: green;")
            
            # 모니터링 시작 시간 업데이트
            start_time = self.price_history[0][0].strftime("%H:%M:%S")
            self.monitor_start_label.setText(f"모니터링 시작: {start_time}")
            
            # 1000달러 이상 하락 감지 시 매수 조건 모니터링 시작
            if price_drop >= 1000 and not self.monitoring_buy_conditions:
                self.monitoring_buy_conditions = True
                self.buy_monitoring_start_time = current_time
                self.buy_monitoring_end_time = current_time + timedelta(minutes=30)
                
                message = (f"⚠️ 비트코인 가격 경고!\n"
                          f"지난 {(current_time - self.price_history[0][0]).total_seconds() // 60}분 동안\n"
                          f"${price_drop:.2f} 하락했습니다.\n"
                          f"현재 가격: ${current_price:,.2f}\n\n"
                          f"향후 30분간 매수 진입 조건을 모니터링합니다.")
                
                self.send_telegram_message(message)
                self.log_message("가격 하락 감지. 매수 조건 모니터링을 시작합니다.")
            
            # 매수 조건 모니터링 중일 때
            elif self.monitoring_buy_conditions:
                # 매수 진입 조건 체크
                buy_conditions_met, conditions_message = self.check_buy_conditions()
                
                if buy_conditions_met:
                    message = (f"✅ 매수 진입 조건 충족!\n"
                              f"현재 가격: ${current_price:,.2f}\n\n"
                              f"{conditions_message}")
                    
                    self.send_telegram_message(message)
                    self.log_message("매수 조건이 충족되었습니다!")
                    self.monitoring_buy_conditions = False
                
                # 30분이 지났는지 체크
                elif current_time >= self.buy_monitoring_end_time:
                    message = (f"❌ 매수 진입 조건 모니터링 종료\n"
                              f"30분 동안 매수 조건이 충족되지 않았습니다.\n"
                              f"현재 가격: ${current_price:,.2f}")
                    
                    self.send_telegram_message(message)
                    self.log_message("매수 조건 모니터링이 종료되었습니다.")
                    self.monitoring_buy_conditions = False

    def update_data(self):
        if not self.monitoring:
            return
            
        current_time = datetime.now()
        current_price = self.get_current_price()
        
        if current_price is not None:
            # 가격 레이블 업데이트
            self.price_label.setText(f"Current Price: ${current_price:,.2f}")
            
            # 데이터 추가
            self.times.append(current_time)
            self.prices.append(current_price)
            
            # 30분 이전 데이터 제거
            while len(self.times) > 0 and (current_time - self.times[0]).total_seconds() > 1800:
                self.times.pop(0)
                self.prices.pop(0)
            
            # 가격 변동 로깅
            if len(self.prices) > 1:
                change = current_price - self.prices[-2]
                self.log_message(f"현재 가격: ${current_price:,.2f} (변동: ${change:+,.2f})")
            
            # 차트 업데이트
            self.ax.clear()
            self.ax.plot(self.times, self.prices, 'g-')
            self.ax.set_title('Bitcoin Price Chart (Last 30 minutes)')
            self.ax.set_xlabel('Time')
            self.ax.set_ylabel('Price (USDT)')
            self.ax.grid(True)
            
            # x축 날짜 포맷 설정
            plt.setp(self.ax.xaxis.get_majorticklabels(), rotation=45)
            self.ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            
            # y축 범위 자동 조정
            if len(self.prices) > 0:
                margin = (max(self.prices) - min(self.prices)) * 0.1
                self.ax.set_ylim(min(self.prices) - margin, max(self.prices) + margin)
            
            self.fig.tight_layout()
            self.canvas.draw()
            
            # 가격 하락 체크
            self.check_price_drop(current_time, current_price)

def main():
    app = QApplication(sys.argv)
    window = BitcoinMonitorGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 