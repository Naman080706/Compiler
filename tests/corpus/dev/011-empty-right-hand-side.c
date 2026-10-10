#include <stdio.h>

int main(void) {
    int readings[5];
    int sum = 0;
    int average;
    int i;
    for (i = 0; i < 5; i++) {
        readings[i] = 20 + i * 3;
        sum += readings[i];
    }
    average = sum / ;
    printf("average = %d\n", average);
    return 0;
}
