#include <stdio.h>

int is_leap(int year) {
    if (year % 400 == 0) {
        return 1;
    }
    if (year % 100 == 0) {
        return 0;
    }
    if (year % 4 == 0) {
        return 1;
    }
    return 0;
}

int main(void) {
    int year;
    int leap;
    for (year = 1896; year <= 1912; year += 4) {
        if (leap = is_leap(year)) {
            printf("%d is a leap year (flag %d)\n", year, leap);
        } else {
            printf("%d is not a leap year\n", year);
        }
    }
    return 0;
}
