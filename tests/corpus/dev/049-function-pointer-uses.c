#include <stdio.h>

int main(void) {
    int i;
    int total = 0;
    int *values;
    values[0] = 4;
    values[1] = 9;
    values[2] = 16;
    for (i = 0; i < 3; i++) {
        total += values[i];
    }
    printf("total = %d, first = %d\n", total, values[0]);
    return 0;
}
