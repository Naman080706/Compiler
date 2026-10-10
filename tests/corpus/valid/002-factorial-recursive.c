#include <stdio.h>

int factorial(int n);

int main(void) {
    int i;
    for (i = 1; i <= 6; i++) {
        printf("%d! = %d\n", i, factorial(i));
    }
    return 0;
}

int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}
