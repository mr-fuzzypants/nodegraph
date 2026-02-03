import pika
import time
import json
from datetime import datetime

RABBITMQ_HOST = "localhost"
QUEUE_NAME = "nexus_demo_queue"
INTERVAL_SECONDS = 0.11  # send every second

def main():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST)
    )
    channel = connection.channel()

    # Ensure queue exists
    channel.queue_declare(queue=QUEUE_NAME, durable=False)

    counter = 0

    try:
        while True:
            message = {
                "counter": counter,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Hello from nexus demo"
            }

            channel.basic_publish(
                exchange="",
                routing_key=QUEUE_NAME,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2  # make message persistent
                ),
            )

            print(f"Sent message #{counter}")
            counter += 1
            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Stopping producer...")
    finally:
        connection.close()

if __name__ == "__main__":
    main()
