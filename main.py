"""
API Agent - Main entry point
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_api():
    """Run FastAPI server"""
    import uvicorn
    from api.routes import app
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


def run_streamlit():
    """Run Streamlit app"""
    import subprocess
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        os.path.join(os.path.dirname(__file__), "streamlit_app.py"),
        "--server.port=8501"
    ])


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="API Agent")
    parser.add_argument(
        "mode",
        choices=["api", "demo", "both"],
        default="demo",
        nargs="?",
        help="Run mode: api (FastAPI), demo (Streamlit), or both"
    )
    
    args = parser.parse_args()
    
    if args.mode == "api":
        run_api()
    elif args.mode == "demo":
        run_streamlit()
    else:
        print("Run with: python main.py api  OR  python main.py demo")