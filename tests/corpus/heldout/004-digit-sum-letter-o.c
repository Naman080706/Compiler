#include <stdio.h>

int digit_sum(int n) {
    int sum = 0;
    while (n > 0) {
        sum += n % 10;
        n = n / 1O;
    }
    return sum;
}

int main(void) {
    int value = 48291;
    printf("digit sum of %d is %d\n", value, digit_sum(value));
    printf("digit sum of 999 is %d\n", digit_sum(999));
    return 0;
}
