import logging
import os
from datetime import datetime

class Logger:
    """Custom logger for CodeSage."""
    
    @staticmethod
    def setup(log_file='logs/codesage.log', level=logging.INFO):
        """Setup logging configuration."""
        
        # Create logs directory if not exists
        os.makedirs('logs', exist_ok=True)
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger('CodeSage')
