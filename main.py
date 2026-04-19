from methods.data_extractor import select_and_extract
from methods.data_processor import hibrid_processor
from methods.df import save_to_xlsx
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    
    start_time = time.time()

    documents = select_and_extract()
    processed_data = hibrid_processor(documents)
 
    save_to_xlsx(processed_data)

    elapsed = time.time() - start_time
    logger.info(f"Tiempo total de ejecución: {elapsed:.2f} segundos")