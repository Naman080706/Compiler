#include <stdio.h>

int power(int base, int exponent) {
    int result = 1;
    int i;
    for (i = 0; i < exponent; i++) {
        result = result * base;
    }
    return result;
}

int main(void) {
    int first = power(2, 10);
    int second = power(3, 4);
    int first = power(5, 3);
    printf("2^10 = %d\n", first);
    printf("3^4 = %d\n", second);
    return 0;
}
