#include <stdio.h>

int main(void) {
    int day = 3;
    int points = 87;
    switch (day) {
        case 1:
            printf("Monday\n");
            break;
        case 2:
        case 3:
            printf("Midweek %d\n", points);
            break;
        default:
            printf("Another day\n");
            break;
    }
    switch (points / 10) {
        case 9:
            printf("A\n");
            break;
        case 8:
            printf("B\n");
        default:
            printf("keep going\n");
    }
    return 0;
}
