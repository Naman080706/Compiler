#include <stdio.h>

int main(void) {
    int i;
    int sum = 0;
    int product = 1;
    for (i = 1; i < 6; i++ {
        sum += i;
        product = product * i;
        printf("i=%d sum=%d product=%d\n", i, sum, product);
    }
    printf("final sum %d product %d\n", sum, product);
    return 0;
}
