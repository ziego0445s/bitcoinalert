import time
from binance.client import Client
import telegram
from datetime import datetime, timedelta
import logging
import os

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

    # update_candle_data와 check_buy_conditions 메소드는 기존 코드와 동일

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