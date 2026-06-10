import warnings
# chardet 6.x no es reconocido por requests 2.x — warning inofensivo, se suprime
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

from frontend.gui import main


if __name__ == "__main__":
    main()
