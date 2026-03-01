"""Запуск веб-интерфейса торгового бота."""

from app import create_app

if __name__ == "__main__":
    app = create_app()
    print("=" * 60)
    print("Supertrend Bot Dashboard zapuschen!")
    print("=" * 60)
    print("\nOtkroyte v brauzere: http://localhost:5001")
    print("\nDlya ostanovki nazhmite Ctrl+C\n")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5001, debug=True)
