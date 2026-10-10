#include <stdio.h>

int main(void) {
    int seconds = 5;
    while (seconds > 0) {
        printf("%d...\n", seconds);
        seconds--;
    }
    if (seconds == 0) {
        printf("Liftoff!\n");
        break;
    }
    printf("countdown over\n");
    return 0;
}
