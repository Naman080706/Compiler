#include <stdio.h>

int main(void) {
    int choice = 2;
    switch (choice) {
        case 1:
            printf("one\n");
            break;
        case 2:
            printf("two\n");
            break;
        case 1:
            printf("uno\n");
            break;
    }
    return 0;
}
