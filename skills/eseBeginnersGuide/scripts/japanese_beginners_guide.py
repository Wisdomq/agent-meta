import os

# Constants
JAPANESE_ALPHABET = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもややゆよらりるれろわをん"
ROMANIZATION_TABLE = {
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'ら': 'ra', 'り': 'ri', 'ろ': 'ro',
    'わ': 'wa', 'を': 'wo', 'ん': 'n'
}

# Main function
def main():
    print("Japanese Beginner's Guide")
    print("\nJapanese is a beautiful and complex language with two primary written forms: Hiragana and Katakana.")
    print("Hiragana consists of 46 basic characters, while Katakana has 24. Both are phonetic scripts used for grammar and native words.")

    print("\nLearning the Japanese Alphabet:")
    print(f"The Japanese alphabet is as follows:\n{JAPANESE_ALPHABET}")

    print("\nRomanization Table:")
    print("Here's a simple table to help you remember the romanization of each character.")
    for char, roman in ROMANIZATION_TABLE.items():
        print(f"{char} : {roman}")

    print("\nPractice and repetition are key to mastering Japanese. Start by learning the alphabet and gradually move on to more complex topics such as grammar and vocabulary.")

if __name__ == "__main__":
    main()