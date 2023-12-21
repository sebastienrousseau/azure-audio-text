import azure.cognitiveservices.speech as speechsdk
import logging
import os
import json
import sqlite3
from dotenv import load_dotenv
import threading

# Load environment variables from .env file
load_dotenv()

# Constants
AUDIO_EXTENSION = os.getenv('AUDIO_EXTENSION')
DB_TABLE_NAME = 'transcriptions'

# Set up logging format
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s app - %(message)s')
logger = logging.getLogger('AzureSpeechToText')


class Config:
    def __init__(self):
        self.api_key = os.getenv('API_KEY')
        self.region = os.getenv('REGION')
        self.input_folder = os.getenv('INPUT_FOLDER')
        self.output_folder = os.getenv('OUTPUT_FOLDER')
        self.validate()

    def validate(self):
        required_vars = [self.api_key, self.region, self.input_folder, self.output_folder, AUDIO_EXTENSION]
        if any(var is None for var in required_vars):
            missing = [var for var, value in locals().items() if value is None]
            logger.error(f"Missing environment variables: {', '.join(missing)}")
            raise EnvironmentError("Missing required environment variables.")


class SpeechToText:
    def __init__(self, config):
        self.config = config

    def process_audio_files(self):
        for filename in os.listdir(self.config.input_folder):
            if filename.endswith(AUDIO_EXTENSION):
                self.process_file(filename)

    def process_file(self, filename):
        input_path = os.path.join(self.config.input_folder, filename)
        output_filename = os.path.splitext(filename)[0]
        output_path = os.path.join(self.config.output_folder, f"{output_filename}.txt")
        json_path = os.path.join(self.config.output_folder, f"{output_filename}.json")
        db_filename = os.path.join(self.config.output_folder, 'transcriptions.db')

        logger.info(f"Processing {input_path}")
        results = self.speech_to_text_long(input_path)

        if results:
            self.write_to_file(output_path, results)
            self.write_to_json(json_path, results)
            self.write_to_sqlite(db_filename, filename, results)

    def speech_to_text_long(self, audio_filename):
        logger.info(f"Starting speech recognition for {audio_filename}. Please wait...")
        speech_config = speechsdk.SpeechConfig(subscription=self.config.api_key, region=self.config.region)
        audio_input = speechsdk.audio.AudioConfig(filename=audio_filename)
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

        all_results = []
        done = threading.Event()

        def handle_final_result(evt):
            logger.info(f"Recognized: {evt.result.text}")
            all_results.append(evt.result.text)

        def handle_recognition_error(evt):
            if evt.result.reason == speechsdk.ResultReason.Canceled:
                cancellation = evt.result.cancellation_details
                if cancellation.reason == speechsdk.CancellationReason.EndOfStream:
                    logger.info("Recognition completed: End of audio stream reached.")
                elif cancellation.reason == speechsdk.CancellationReason.Error:
                    logger.error(f"Recognition canceled due to an error: {cancellation.error_details}")
                else:
                    logger.error(f"Recognition canceled: Reason={cancellation.reason}")
            else:
                logger.error(f"Recognition error: {evt}")
            done.set()

        speech_recognizer.recognized.connect(handle_final_result)
        speech_recognizer.canceled.connect(handle_recognition_error)
        speech_recognizer.session_stopped.connect(lambda evt: done.set())

        speech_recognizer.start_continuous_recognition()
        done.wait()

        if not all_results:
            logger.warning(f"No results for {audio_filename}. Check the audio file format and content.")

        return all_results

    def write_to_file(self, output_filename, results):
        with open(output_filename, 'w') as file:
            for result in results:
                file.write(result + "\n")

    def write_to_json(self, json_filename, results):
        with open(json_filename, 'w') as json_file:
            json.dump(results, json_file, indent=4)

    def write_to_sqlite(self, db_filename, audio_filename, results):
        with sqlite3.connect(db_filename) as conn:
            cursor = conn.cursor()
            cursor.execute(f'''CREATE TABLE IF NOT EXISTS {DB_TABLE_NAME}
                              (filename TEXT, transcription TEXT)''')
            for result in results:
                cursor.execute(f"INSERT INTO {DB_TABLE_NAME} (filename, transcription) VALUES (?, ?)",
                               (audio_filename, result))
            conn.commit()


def run_speech_to_text_process():
    try:
        config = Config()
        if not os.path.exists(config.output_folder):
            os.makedirs(config.output_folder)

        speech_to_text_processor = SpeechToText(config)
        speech_to_text_processor.process_audio_files()
    except Exception as e:
        logger.error(f"Script execution failed: {e}")


if __name__ == "__main__":
    run_speech_to_text_process()
