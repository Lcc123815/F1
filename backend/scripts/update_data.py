import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_service import get_stock_basic, batch_update_daily_data

if __name__ == "__main__":
    print("开始更新数据...")
    get_stock_basic()          # 先更新股票列表
    batch_update_daily_data(10) # 再更新10只股票日线（测试用）