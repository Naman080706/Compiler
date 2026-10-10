#include <stdio.h>

int main(void) {
    int i;
    int evens = 0;
    int i;
    for (i = 0; i < 20; i++) {
        if (i % 2 == 0) {
            evens++;
        }
    }
    printf("%d even numbers below 20\n", evens);
    return 0;
}
