#include <stdio.h>

int mian(void) {
    int i;
    int product = 1;
    for (i = 1; i <= 5; i++) {
        product = product * i;
    }
    printf("5! = %d\n", product);
    return 0;
}
