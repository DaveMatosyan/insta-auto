"""
Merge multiple CSV files and create a master username tracker
Extracts only usernames and adds a 'used' boolean column
Prevents duplicate entries
"""

import os
import csv
from pathlib import Path

# Configuration - look for csv_files folder in same directory
CSV_FOLDER = os.path.join(os.path.dirname(__file__), "csv_files")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "usernames_tracker.csv")
SEMICOLON_DELIMITER = ";"  # CSV files use semicolon as delimiter


def merge_csv_files(input_folder=CSV_FOLDER, output_file=OUTPUT_FILE):
    """
    Merge all CSV files in a folder, extract usernames, remove duplicates
    
    Args:
        input_folder: Folder containing CSV files
        output_file: Path to output merged CSV file
    """
    
    # Check if csv_files folder exists
    if not os.path.exists(input_folder):
        print(f"⚠️ Folder not found: {input_folder}")
        print(f"Creating folder...")
        os.makedirs(input_folder, exist_ok=True)
        print(f"✓ Created: {input_folder}")
        print(f"⚠️ Please place your CSV files in: {input_folder}")
        return False
    
    usernames_dict = {}  # {username: used_status}
    
    # Find all CSV files
    csv_files = list(Path(input_folder).glob("*.csv"))
    
    if not csv_files:
        print("⚠️ No CSV files found in the folder!")
        return False
    
    print(f"Found {len(csv_files)} CSV files:")
    for f in csv_files:
        print(f"  - {f.name}")
    
    # Process each CSV file
    total_items = 0
    total_duplicates = 0
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                # Try to detect delimiter (semicolon or comma)
                sample = f.read(1024)
                f.seek(0)
                
                if ';' in sample and ',' in sample:
                    delimiter = ';'
                elif ';' in sample:
                    delimiter = ';'
                else:
                    delimiter = ','
                
                reader = csv.DictReader(f, delimiter=delimiter)
                
                if not reader.fieldnames:
                    print(f"⚠️ {csv_file.name}: Could not read headers, skipping...")
                    continue
                
                # Find username column (try different variations)
                username_column = None
                for col in reader.fieldnames:
                    if col.lower().strip() == "username":
                        username_column = col
                        break
                
                if not username_column:
                    print(f"⚠️ {csv_file.name}: 'username' column not found, skipping...")
                    print(f"   Available columns: {reader.fieldnames}")
                    continue
                
                print(f"\n📄 Processing {csv_file.name}...")
                file_count = 0
                
                for row in reader:
                    username = row.get(username_column, "").strip()
                    
                    if username:  # Only process non-empty usernames
                        if username not in usernames_dict:
                            usernames_dict[username] = False  # False = not used
                            file_count += 1
                        else:
                            total_duplicates += 1
                
                print(f"  ✓ Added {file_count} new usernames")
                total_items += file_count
                
        except Exception as e:
            print(f"❌ Error processing {csv_file.name}: {e}")
    
    # Write merged file
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['username', 'used'])
            
            for username, used in sorted(usernames_dict.items()):
                writer.writerow([username, used])
        
        print(f"\n{'='*60}")
        print(f"✓ Merged file created: {os.path.basename(output_file)}")
        print(f"Location: {output_file}")
        print(f"{'='*60}")
        print(f"Total unique usernames: {len(usernames_dict)}")
        print(f"Duplicates skipped: {total_duplicates}")
        print(f"{'='*60}\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Error writing output file: {e}")
        return False


if __name__ == "__main__":
    merge_csv_files()
