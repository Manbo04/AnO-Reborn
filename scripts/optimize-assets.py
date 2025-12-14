#!/usr/bin/env python3
"""
Asset optimization script for reducing file sizes
Run: python3 scripts/optimize-assets.py
"""
import re
import os
from pathlib import Path


def minify_css(css_content):
    """Minify CSS by removing comments, whitespace, and unnecessary characters"""
    # Remove comments
    css_content = re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)
    # Remove tabs, newlines, carriage returns
    css_content = re.sub(r"[\r\n\t]+", " ", css_content)
    # Remove spaces around certain characters
    css_content = re.sub(r"\s*([{}:;,>+~])\s*", r"\1", css_content)
    # Remove last semicolon in rule
    css_content = re.sub(r";}", "}", css_content)
    # Remove spaces before !important
    css_content = re.sub(r"\s+!important", "!important", css_content)
    # Collapse multiple spaces
    css_content = re.sub(r"\s+", " ", css_content)
    return css_content.strip()


def minify_js(js_content):
    """Minify JavaScript by removing comments and excess whitespace"""
    # Remove single-line comments
    js_content = re.sub(r"//.*?$", "", js_content, flags=re.MULTILINE)
    # Remove multi-line comments
    js_content = re.sub(r"/\*.*?\*/", "", js_content, flags=re.DOTALL)
    # Remove tabs and excessive newlines
    js_content = re.sub(r"[\t\r]+", "", js_content)
    js_content = re.sub(r"\n\s*\n", "\n", js_content)
    # Remove spaces around certain operators
    js_content = re.sub(r"\s*([{}()[\]:;,=+\-*/<>!&|?])\s*", r"\1", js_content)
    # Restore spaces after keywords
    js_content = re.sub(
        r"(if|else|for|while|function|return|var|let|const)([({])", r"\1 \2", js_content
    )
    return js_content.strip()


def optimize_css_files():
    """Minify all CSS files"""
    static_dir = Path(__file__).parent.parent / "static"
    css_files = list(static_dir.glob("*.css"))

    for css_file in css_files:
        if css_file.name.endswith(".min.css"):
            continue

        print(f"Processing {css_file.name}...")
        with open(css_file, "r", encoding="utf-8") as f:
            content = f.read()

        original_size = len(content)
        minified = minify_css(content)
        minified_size = len(minified)

        # Save minified version
        min_file = css_file.with_stem(css_file.stem + ".min")
        with open(min_file, "w", encoding="utf-8") as f:
            f.write(minified)

        reduction = ((original_size - minified_size) / original_size) * 100
        print(
            f"  Original: {original_size}B → Minified: {minified_size}B (saved {reduction:.1f}%)"
        )


def optimize_js_files():
    """Minify all JS files"""
    static_dir = Path(__file__).parent.parent / "static"
    js_files = [f for f in static_dir.glob("*.js") if not f.name.endswith(".min.js")]

    for js_file in js_files:
        print(f"Processing {js_file.name}...")
        with open(js_file, "r", encoding="utf-8") as f:
            content = f.read()

        original_size = len(content)
        minified = minify_js(content)
        minified_size = len(minified)

        # Save minified version
        min_file = js_file.with_stem(js_file.stem + ".min")
        with open(min_file, "w", encoding="utf-8") as f:
            f.write(minified)

        reduction = ((original_size - minified_size) / original_size) * 100
        print(
            f"  Original: {original_size}B → Minified: {minified_size}B (saved {reduction:.1f}%)"
        )


if __name__ == "__main__":
    print("🚀 Starting asset optimization...\n")
    print("CSS Optimization:")
    optimize_css_files()
    print("\nJavaScript Optimization:")
    optimize_js_files()
    print("\n✅ Optimization complete!")
    print("\nNext steps:")
    print("1. Update templates to reference .min.css and .min.js files")
    print("2. Test the application thoroughly")
    print("3. Delete original non-minified files if satisfied")
