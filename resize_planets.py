import os
import glob
from PIL import Image

def main():
    search_path = "/Users/dede/AnO-Reborn/static/img/planet_*.jpg"
    files = glob.glob(search_path)
    
    if not files:
        print(f"No files found matching {search_path}")
        return

    print(f"Found {len(files)} files to resize.")
    
    for file_path in files:
        try:
            with Image.open(file_path) as img:
                # Resize to 512x512
                img_resized = img.resize((512, 512), Image.Resampling.LANCZOS)
                
                # Overwrite original, with 70% quality
                img_resized.save(file_path, "JPEG", quality=70, optimize=True)
                print(f"Successfully resized and saved {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    main()
