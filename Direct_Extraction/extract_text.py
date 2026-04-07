#!/usr/bin/env python3
"""
Journal Officiel PDF Text Extractor
Extracts text from multi-column PDF layouts with footer removal
Based on ocr_watchdog.py logic but using direct PDF extraction
"""

import os
import argparse
import re
from pathlib import Path
import pdfplumber
from tqdm import tqdm
from typing import Dict, Optional

# === Configuration (matching ocr_watchdog.py logic) ===
# 350 pixels at 300 DPI = ~84 points (350/300*72)
FOOTER_CROP_HEIGHT = 84  # Points to crop from bottom (footer removal)


def extract_pdf_text(pdf_path: str, output_dir: str = "extracted_text") -> Optional[Dict]:
    """
    Extract text from a single PDF with footer cropping and 3-column layout handling
    
    Args:
        pdf_path: Path to input PDF file
        output_dir: Directory for output text files
        
    Returns:
        Dictionary with metadata (filename, issue, year, pages, output path)
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            all_text = []
            
            for page_num, page in enumerate(pdf.pages, 1):
                # Get page dimensions
                width = page.width
                height = page.height
                
                # Crop footer (like ocr_watchdog.py: removes bottom 350px)
                cropped_page = page.crop((0, 0, width, height - FOOTER_CROP_HEIGHT))
                height = cropped_page.height
                
                # Extract text handling 3-column layout
                col_width = width / 3
                columns = []
                
                for i in range(3):
                    x0 = i * col_width
                    x1 = (i + 1) * col_width
                    col_bbox = (x0, 0, x1, height)
                    col_crop = cropped_page.crop(col_bbox)
                    col_text = col_crop.extract_text()
                    if col_text:
                        columns.append(col_text.strip())
                
                # Join columns or fallback to full page
                if any(columns):
                    page_text = "\n\n[COLUMN BREAK]\n\n".join(col for col in columns if col)
                else:
                    page_text = cropped_page.extract_text() or ""
                
                all_text.append(f"\n--- Page {page_num} ---\n{page_text}")
            
            full_text = "\n".join(all_text)
            
            # Save extracted text
            rel_path = os.path.relpath(pdf_path, "doc")
            output_path = os.path.join(output_dir, rel_path.replace('.pdf', '.txt'))
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            
            # Extract basic metadata
            filename = os.path.basename(pdf_path)
            issue_match = re.search(r'(\d+)Journal', filename)
            year_match = re.search(r'(\d{4})', filename)
            
            metadata = {
                'filename': filename,
                'issue': issue_match.group(1) if issue_match else '?',
                'year': year_match.group(1) if year_match else '?',
                'pages': len(pdf.pages),
                'output': output_path
            }
            
            return metadata
            
    except Exception as e:
        print(f"❌ Error: {pdf_path} - {e}")
        return None


def find_all_pdfs(base_dir: str) -> list:
    """Find all PDF files in directory tree"""
    pdf_files = []
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith('.pdf'):
                pdf_files.append(os.path.join(root, file))
    return sorted(pdf_files)


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(
        description='Extract text from Journal Officiel PDFs with footer removal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --year 2014                  # Extract all PDFs from 2014
  %(prog)s --year 2014 --limit 10       # Extract first 10 PDFs from 2014
  %(prog)s --input doc --output texts   # Custom input/output directories
  %(prog)s                              # Extract all PDFs (may take hours!)
        """
    )
    parser.add_argument('--year', type=str, help='Specific year to process (e.g., 2014)')
    parser.add_argument('--input', type=str, default='doc', help='Input directory (default: doc)')
    parser.add_argument('--output', type=str, default='extracted_text', help='Output directory (default: extracted_text)')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("PDF TEXT EXTRACTOR - Journal Officiel")
    print("Footer Cropping: ON (removes bottom 350px like ocr_watchdog.py)")
    print("="*80 + "\n")
    
    # Find PDFs
    search_path = os.path.join(args.input, args.year) if args.year else args.input
    
    if not os.path.exists(search_path):
        print(f"❌ Directory not found: {search_path}")
        return
    
    pdf_files = find_all_pdfs(search_path)
    
    if args.limit:
        pdf_files = pdf_files[:args.limit]
    
    if not pdf_files:
        print(f"❌ No PDFs found in {search_path}")
        return
    
    print(f"📚 Found {len(pdf_files)} PDFs")
    if args.year:
        print(f"📅 Processing year: {args.year}")
    if args.limit:
        print(f"🔢 Limit: {args.limit} files")
    print()
    
    # Process PDFs
    results = []
    for pdf_path in tqdm(pdf_files, desc="Processing PDFs", unit="file"):
        result = extract_pdf_text(pdf_path, args.output)
        if result:
            results.append(result)
    
    # Summary
    print(f"\n✅ Successfully extracted {len(results)}/{len(pdf_files)} PDFs")
    print(f"📁 Output directory: {args.output}")
    
    # Group by year
    by_year = {}
    for r in results:
        year = r['year']
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(r)
    
    print("\n📊 Summary by year:")
    for year in sorted(by_year.keys()):
        total_pages = sum(r['pages'] for r in by_year[year])
        print(f"   {year}: {len(by_year[year])} files, {total_pages} pages")
    print()


if __name__ == "__main__":
    main()
