import time
import logging
import board
import busio
import adafruit_bmp280
import adafruit_scd30
import adafruit_sht31d
import paho.mqtt.client as mqtt
import json

# Setup basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(message)s')

# Configuration
MQTT_BROKER = "192.168.1.176"  # Replace with your Pi 4's IP address
MQTT_PORT = 1883
MQTT_TOPICS = {
    "external": {
        "temperature": "weather_station/external/temperature",
        "humidity": "weather_station/external/humidity",
        "pressure": "weather_station/external/pressure",
        "co2": "weather_station/external/co2",
    },
    "pre-con": {
        "temperature": "weather_station/precon/temperature",
        "humidity": "weather_station/precon/humidity",
    },
}
I2C_SCD30_ADDRESS = 0x61
I2C_BMP280_ADDRESS = 0x77
PUBLISH_INTERVAL = 10  # seconds
BOX_ID = "box_1"  # Add your box ID here

# Initialize sensors
def initialize_sensors():
    try:
        # I2C for external sensors (BMP280 and SCD-30)
        i2c_external = busio.I2C(board.SCL, board.SDA)
        bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c_external, address=I2C_BMP280_ADDRESS)
        scd30 = adafruit_scd30.SCD30(i2c_external)

        # Configure BMP280
        bmp280.sea_level_pressure = 1013.25  # Adjust based on your location

        # I2C for pre-con sensor (SHT31)
        i2c_precon = busio.I2C(board.D5, board.D6)  # GPIO 5 (SCL), GPIO 6 (SDA)
        sht31 = adafruit_sht31d.SHT31D(i2c_precon)

        logging.debug("All sensors initialized successfully")

        return bmp280, scd30, sht31
    except Exception as e:
        logging.critical(f"Failed to initialize sensors: {e}")
        return None, None, None

# MQTT connect callback
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
    else:
        logging.error(f"Failed to connect, return code {rc}")

# MQTT disconnect callback
def on_disconnect(client, userdata, rc):
    logging.warning("Disconnected from MQTT broker. Trying to reconnect...")
    while True:
        try:
            client.reconnect()
            break
        except Exception as e:
            logging.error(f"Reconnection failed: {e}")
            time.sleep(5)

# Read and publish data
def read_and_publish(bmp280, scd30, sht31, client):
    try:
        # Read external sensor data
        temp_bmp = bmp280.temperature
        pressure = bmp280.pressure
        temp_scd = scd30.temperature
        humidity_scd = scd30.relative_humidity
        co2 = scd30.CO2

        # Read pre-con sensor data
        temp_precon = sht31.temperature
        humidity_precon = sht31.relative_humidity

        # Prepare sensor data dictionary
        sensor_data = {
            'box_id': BOX_ID,
            'external': {
                'temperature': temp_bmp,
                'pressure': pressure,
                'humidity': humidity_scd,
                'co2': co2
            },
            'pre-con': {
                'temperature': temp_precon,
                'humidity': humidity_precon
            }
        }

        # Publish external data
        if client:
            client.publish(MQTT_TOPICS['external']['temperature'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['external']['temperature']}))
            client.publish(MQTT_TOPICS['external']['pressure'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['external']['pressure']}))
            client.publish(MQTT_TOPICS['external']['humidity'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['external']['humidity']}))
            client.publish(MQTT_TOPICS['external']['co2'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['external']['co2']}))

            # Publish pre-con data
            client.publish(MQTT_TOPICS['pre-con']['temperature'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['pre-con']['temperature']}))
            client.publish(MQTT_TOPICS['pre-con']['humidity'], json.dumps({'box_id': BOX_ID, 'value': sensor_data['pre-con']['humidity']}))

        # Log published data
        logging.info(f"Published sensor data: {sensor_data}")

    except Exception as e:
        logging.error(f"Error reading sensors or publishing data: {e}")

def main():
    # Initialize MQTT client
    client = None
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
    except Exception as e:
        logging.critical(f"MQTT connection failed: {e}")
        client = None  # Set client to None if connection fails

    # Initialize sensors
    bmp280, scd30, sht31 = initialize_sensors()
    if not (bmp280 and scd30 and sht31):
        logging.critical("Sensor initialization failed. Exiting.")
        return

    # Main loop
    try:
        while True:
            read_and_publish(bmp280, scd30, sht31, client)
            time.sleep(PUBLISH_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Program terminated by user.")
    finally:
        # Ensure graceful MQTT shutdown
        if client:
            logging.info("Stopping MQTT loop...")
            client.loop_stop()
            client.disconnect()

if __name__ == "__main__":
    main()