#include <stdio.h>

int main(void) {
    int sum = 0;
    int i;
    double average = ;
    for (i = 1; i <= 5; i++) {
        sum += i * 4;
    }
    average = sum / 5.0;
    printf("average = %f\n", average);
    if (average > 10.0) {
        printf("above ten: %f\n", average);
    }
    return 0;
}
