#include <stdio.h>

int main(void) {
    int evens = 0;
    int odds = 0;
    int n;
    for (n = 1; n <= 20; n++) {
        if (n % 2 == 0) {
            evens = evens + `1;
        } else {
            odds = odds + 1;
        }
    }
    printf("evens: %d\n", evens);
    printf("odds: %d\n", odds);
    return 0;
}
