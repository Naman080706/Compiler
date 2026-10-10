#include <stdio.h>

int main(void) {
    double prices[3];
    double sum = 0.0;
    int i;
    int whole = 7.9;
    prices[0] = 2.5;
    prices[1] = 4.25;
    prices[2] = 1.75;
    for (i = 0; i < 3; i++) {
        sum += prices[i];
    }
    printf("sum of prices: %f\n", sum);
    printf("whole part of 7.9: %d\n", whole);
    printf("rounded up: %d\n", whole + 1);
    return 0;
}
