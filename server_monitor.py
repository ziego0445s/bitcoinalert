import time
from binance.client import Client
import telegram
from datetime import datetime, timedelta
import logging
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 환경 변수에서 API 키 가져오기
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# API 키 확인
if not all([BINANCE_API_KEY, BINANCE_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logger.error("필요한 환경 변수가 설정되지 않았습니다.")
    raise ValueError("환경 변수 설정이 필요합니다.")

class BitcoinMonitorServer:
    def __init__(self):
        self.price_history = []
        self.candle_data = []
        self.last_candle_time = None
        self.monitoring_buy_conditions = False
        self.buy_monitoring_start_time = None
        self.buy_monitoring_end_time = None
        
        # Binance 클라이언트 및 텔레그램 봇 초기화
        self.binance_client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        
        logger.info("Bitcoin 모니터링 서버가 시작되었습니다.")

    def get_current_price(self):
        try:
            ticker = self.binance_client.get_symbol_ticker(symbol="BTCUSDT")
            return float(ticker['price'])
        except Exception as e:
            logger.error(f"가격 조회 중 오류 발생: {e}")
            return None

    def send_telegram_message(self, message):
        try:
            self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            logger.info("텔레그램 메시지 전송 완료")
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 중 오류 발생: {e}")

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

    def monitor_price(self):
        while True:
            try:
                current_time = datetime.now()
                current_price = self.get_current_price()
                
                if current_price is not None:
                    # 기존의 check_price_drop 로직
                    self.price_history.append((current_time, current_price))
                    self.price_history = [x for x in self.price_history 
                                        if x[0] > current_time - timedelta(minutes=30)]
                    
                    self.update_candle_data(current_time, current_price)
                    
                    if len(self.price_history) > 1:
                        oldest_price = self.price_history[0][1]
                        price_drop = oldest_price - current_price
                        
                        logger.info(f"현재 가격: ${current_price:,.2f} (30분 변동: ${-price_drop:+,.2f})")
                        
                        if price_drop >= 1000 and not self.monitoring_buy_conditions:
                            # 매수 조건 모니터링 시작 로직
                            self.monitoring_buy_conditions = True
                            self.buy_monitoring_start_time = current_time
                            self.buy_monitoring_end_time = current_time + timedelta(minutes=30)
                            
                            message = (f"⚠️ 비트코인 가격 경고!\n"
                                     f"지난 {(current_time - self.price_history[0][0]).total_seconds() // 60}분 동안\n"
                                     f"${price_drop:.2f} 하락했습니다.\n"
                                     f"현재 가격: ${current_price:,.2f}\n\n"
                                     f"향후 30분간 매수 진입 조건을 모니터링합니다.")
                            
                            self.send_telegram_message(message)
                            logger.info("가격 하락 감지. 매수 조건 모니터링을 시작합니다.")
                        
                        elif self.monitoring_buy_conditions:
                            # 매수 조건 체크 로직
                            buy_conditions_met, conditions_message = self.check_buy_conditions()
                            
                            if buy_conditions_met:
                                message = (f"✅ 매수 진입 조건 충족!\n"
                                         f"현재 가격: ${current_price:,.2f}\n\n"
                                         f"{conditions_message}")
                                
                                self.send_telegram_message(message)
                                logger.info("매수 조건이 충족되었습니다!")
                                self.monitoring_buy_conditions = False
                            
                            elif current_time >= self.buy_monitoring_end_time:
                                message = (f"❌ 매수 진입 조건 모니터링 종료\n"
                                         f"30분 동안 매수 조건이 충족되지 않았습니다.\n"
                                         f"현재 가격: ${current_price:,.2f}")
                                
                                self.send_telegram_message(message)
                                logger.info("매수 조건 모니터링이 종료되었습니다.")
                                self.monitoring_buy_conditions = False
                
                time.sleep(60)  # 1분 대기
                
            except Exception as e:
                logger.error(f"모니터링 중 오류 발생: {e}")
                time.sleep(60)  # 오류 발생 시 1분 대기 후 재시도

if __name__ == "__main__":
    monitor = BitcoinMonitorServer()
    monitor.monitor_price() 