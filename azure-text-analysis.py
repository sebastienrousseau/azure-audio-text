import asyncio
import datetime
import os
import json
import sqlite3
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics.aio import TextAnalyticsClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set environment variables
AZURE_LANGUAGE_ENDPOINT = os.getenv('AZURE_LANGUAGE_ENDPOINT')
AZURE_LANGUAGE_KEY = os.getenv('AZURE_LANGUAGE_KEY')
DB_TABLE_NAME = 'text_analysis'
INPUT_FOLDER = os.getenv('OUTPUT_FOLDER')

def convert_to_serializable(obj):
    """
    Converts Azure Text Analytics result objects into a serializable format.
    """
    if isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        obj_dict = {key: convert_to_serializable(value) for key, value in obj.__dict__.items()}
        # Special handling for models with properties that need custom handling
        if hasattr(obj, 'sentences'):
            obj_dict['sentences'] = [convert_to_serializable(sentence) for sentence in obj.sentences]
        if hasattr(obj, 'entities'):
            obj_dict['entities'] = [convert_to_serializable(entity) for entity in obj.entities]
        # Add more conditions as needed for other types
        return obj_dict
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    else:
        return str(obj)  # Fallback to string representation

async def analyze_text(client, document):
    # Perform various text analytics tasks
    async with client:
        sentiment_result = await client.analyze_sentiment([document])
        entity_result = await client.recognize_entities([document])
        key_phrases_result = await client.extract_key_phrases([document])
        language_result = await client.detect_language([document])
        pii_result = await client.recognize_pii_entities([document])
        
        # Add other analyses as needed

    return {
        "sentiment": sentiment_result if sentiment_result else None,
        "entities": entity_result if entity_result else None,
        "key_phrases": key_phrases_result if key_phrases_result else None,
        "language": language_result if language_result else None,
        "pii": pii_result if pii_result else None
        # Add other results as needed
    }

async def process_text_files(client, input_folder):
    print(f"Input folder: {input_folder}")
    for filename in os.listdir(input_folder):
        if filename.endswith('.txt'):
            file_path = os.path.join(input_folder, filename)
            print(f"Processing file: {filename}")
            with open(file_path, 'r') as file:
                text = file.read()
                analysis_results = await analyze_text(client, text)
                print(f"Analysis results for {filename}: {analysis_results}")
                await save_results(filename, analysis_results)

async def save_results(filename, results):
    # Create 'Analysis' folder if it doesn't exist
    analysis_folder = 'Analysis'
    if not os.path.exists(analysis_folder):
        os.makedirs(analysis_folder)

    # Modify the path to save files inside the 'Analysis' folder
    base_filename = os.path.splitext(filename)[0]

    # Save to TXT with plain text format
    txt_filename = os.path.join(analysis_folder, f'{base_filename}_analysis.txt')
    with open(txt_filename, 'w') as file:
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Executive summary format
        file.write('Transcription analysis\n\n')
        file.write(f'File: {filename}\n')
        file.write(f'Time: {current_time}\n\n')
        file.write(f'Summary:\n')

        # Sentiment Analysis Summary
        sentiment_result = results['sentiment'][0]
        file.write(f'   • Overall Sentiment: {sentiment_result.sentiment}.\n')

        # Enhanced Sentiment Analysis Summary
        sentiment_scores = sentiment_result.confidence_scores
        file.write(f'   • Sentiment Scores - Positive: {sentiment_scores.positive:.2f}, Neutral: {sentiment_scores.neutral:.2f}, Negative: {sentiment_scores.negative:.2f}\n')

        # Key Entities Summary
        entities_result = results['entities'][0]
        if entities_result.entities:
            file.write('   • Key Entities Identified: ' + ', '.join([entity.text for entity in entities_result.entities[:5]]) + '.\n')

        # Enhanced Key Phrases Summary
        key_phrases_result = results['key_phrases'][0]
        if key_phrases_result.key_phrases:
            file.write('   • Notable Topics: ' + ', '.join(key_phrases_result.key_phrases[:5]) + '.\n')

        # Language Detection Summary
        language_result = results['language'][0]
        file.write(f'   • Detected Language: {language_result.primary_language.name} ({language_result.primary_language.iso6391_name}).\n')

        # PII Summary (if applicable)
        pii_result = results['pii'][0]
        if pii_result.entities:
            file.write('   • Personally identifiable information (PII): Yes.\n')
        else:
            file.write('   • Personally identifiable information (PII): No.\n')

    print(f'Saving results to {txt_filename}')

    # Save to JSON
    json_filename = os.path.join(analysis_folder, f'{base_filename}_analysis.json')
    with open(json_filename, 'w') as json_file:
        json.dump(convert_to_serializable(results), json_file, indent=4)
    print(f'Saving results to {json_filename}')

    # Save to SQLite
    db_filename = os.path.join(analysis_folder, 'text_analysis.db')
    with sqlite3.connect(db_filename) as conn:
        cursor = conn.cursor()
        cursor.execute(f'''CREATE TABLE IF NOT EXISTS {DB_TABLE_NAME}
                          (filename TEXT, analysis TEXT)''')
        cursor.execute(f"INSERT INTO {DB_TABLE_NAME} (filename, analysis) VALUES (?, ?)",
                       (filename, json.dumps(convert_to_serializable(results))))
        conn.commit()
    print(f'Saved analysis of {filename} to database.')


async def main():
    endpoint = AZURE_LANGUAGE_ENDPOINT
    key = AZURE_LANGUAGE_KEY
    client = TextAnalyticsClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    input_folder = INPUT_FOLDER
    await process_text_files(client, input_folder)

if __name__ == '__main__':
    asyncio.run(main())
