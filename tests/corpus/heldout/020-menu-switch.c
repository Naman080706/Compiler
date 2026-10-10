#include <stdio.h>

int main(void) {
    int day = 3;
    printf("Day number %d\n", day);
    switch (day) {
        case 1:
            printf("Monday\n");
            break;
        case 2:
            printf("Tuesday\n");
            break;
        case 3:
            printf("Wednesday\n");
            break;
        default:
            printf("Another day\n");
    }
    printf("menu finished\n");
    return 0;
}
