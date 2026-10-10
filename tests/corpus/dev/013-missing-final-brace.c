#include <stdio.h>

int square(int x) {
    return x * x;
}

int main(void) {
    int i;
    for (i = 1; i <= 5; i++) {
        printf("%d squared is %d\n", i, square(i));
    }
    return 0;
