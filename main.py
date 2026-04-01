from doc_extraction import select_and_extract
from interpreter import multiple_processing
from data_storage import save_to_xlsx
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    
    start_time = time.time()

    documents = select_and_extract()
    results = []

    for doc in documents:
        print(doc.name, doc.method, doc.ok, doc.text)
        if not doc.ok:
            continue

        text_to_process = doc.text[:2000]
        
        data = multiple_processing(doc.text, doc.path)

        results.append({
            "file": doc.name,
            "data": data
        })

    save_to_xlsx(results)

    elapsed = time.time() - start_time
    logger.info(f"Tiempo total de ejecución: {elapsed:.2f} segundos")