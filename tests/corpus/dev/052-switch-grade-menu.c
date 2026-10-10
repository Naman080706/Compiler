#include <stdio.h>

int main(void) {
    int band = 2;
    int points = 87;
    switch (band) {
        case 1:
            printf("excellent: %d\n", points);
            break;
        case 2:
            printf("good: %d\n", points);
            break;
        default:
            printf("review: %d\n", points);
    }
    printf("band %d, points %d\n", band, points);
    return 0;
}
