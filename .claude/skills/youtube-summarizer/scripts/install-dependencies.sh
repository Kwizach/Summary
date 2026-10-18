#!/usr/bin/env bash
# Install youtube-transcript-api dependency

set -e

echo "📦 Installing youtube-transcript-api..."

if command -v pip3 &>/dev/null; then
    pip3 install -U "youtube-transcript-api>=1.0"
    echo "✅ Installation complete using pip3!"
elif command -v pip &>/dev/null; then
    pip install -U "youtube-transcript-api>=1.0"
    echo "✅ Installation complete using pip!"
else
    echo "❌ Error: pip not found"
    echo "Please install Python pip first:"
    echo "  macOS: brew install python3"
    echo "  Ubuntu/Debian: sudo apt install python3-pip"
    echo "  Fedora: sudo dnf install python3-pip"
    exit 1
fi

# Verify installation
python3 -c "import youtube_transcript_api; print('✅ youtube-transcript-api is ready to use!')" 2>/dev/null || {
    echo "⚠️  Installation completed but verification failed"
    echo "Try running: python3 -c 'import youtube_transcript_api'"
    exit 1
}
