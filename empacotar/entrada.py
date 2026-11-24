"""Ponto de entrada do .exe (o PyInstaller precisa de um script sem import relativo)."""
import sys
import traceback

if __name__ == "__main__":
    try:
        from cortes_gratis.__main__ import main
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        # Sem isto, um erro fecharia a janela antes de dar tempo de ler.
        traceback.print_exc()
        if getattr(sys, "frozen", False):
            input("\nDeu erro. Tire um print desta janela e aperte Enter pra fechar...")
        sys.exit(1)
