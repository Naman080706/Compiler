#include <stdio.h>

int larger(int a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}

int main(void) {
    int readings[6];
    int best, i;
    int lowest = 1000;
    readings[0] = 14;
    readings[1] = 87;
    readings[2] = 33;
    readings[3] = 62;
    readings[4] = 9;
    readings[5] = 45;
    best = readings[0];
    for (i = 0; i < 6; i++) {
        best = larger(best, readings[i]);
        if (readings[i] < lowest && readings[i] >= 0) {
            lowest = readings[i];
        }
    }
    printf("largest = %d, smallest = %d\n", best, lowest);
    return 0;
}
