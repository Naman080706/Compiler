#include <stdio.h>

int main(void) {
    int count = 0;
    int i;
    for (i = 0; i < 20; i++) {
        if (i % 3 == 0) {
            count++;
        }
    }
    printf("multiples of 3 below 20: %d\n", count);
    0 = count;
    printf("after reset: %d\n", count);
    return 0;
}
