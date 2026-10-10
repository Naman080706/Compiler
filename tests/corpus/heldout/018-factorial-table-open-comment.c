#include <stdio.h>

int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

int main(void) {
    int i;
    for (i = 1; i <= 8; i++) {
        printf("%d! = %d\n", i, factorial(i));
    }
    /* TODO: also print the sum of the factorials
    int total = 0;
    for (i = 1; i <= 8; i++) {
        total += factorial(i);
    }
    printf("sum = %d\n", total);
    return 0;
}
