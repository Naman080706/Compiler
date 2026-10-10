#include <stdio.h>

int main(void) {
    char letter = 'a';
    char upper;
    int vowels = 0;
    while (letter <= 'z') {
        if (letter == 'a' || letter == 'e' || letter == 'i' || letter == 'o' || letter == 'u') {
            vowels++;
        }
        letter = letter + 1;
    }
    upper = 'a' - 32;
    printf("%d vowels, first capital %c\n", vowels, upper);
    upper = 'z' - 32;
    printf("last capital %c\n", upper);
    return 0;
}
