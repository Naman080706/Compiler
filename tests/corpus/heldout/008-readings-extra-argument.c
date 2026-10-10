#include <stdio.h>

int larger(int a, int b) {
    if (a > b) {
        return a;
    }
    return b;
}

int main(void) {
    int readings[5];
    int highest;
    int lowest;
    int sum = 0;
    int i;
    readings[0] = 21;
    readings[1] = 17;
    readings[2] = 30;
    readings[3] = 12;
    readings[4] = 25;
    highest = readings[0];
    lowest = readings[0];
    for (i = 0; i < 5; i++) {
        sum += readings[i];
        highest = larger(highest, readings[i], 0);
        if (readings[i] < lowest) {
            lowest = readings[i];
        }
    }
    printf("max %d min %d avg %d\n", highest, lowest, sum / 5);
    return 0;
}
