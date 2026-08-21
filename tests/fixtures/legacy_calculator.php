<?php

require_once "vendor/autoload.php";

use App\Utils\Logger;

class LegacyCalculator
{
    public function soma($a, $b)
    {
        $total = $a + $b;
        return $total;
    }

    private function audit($message)
    {
        Logger::log($message);
    }
}

function calc_helper($value)
{
    return $value * 2;
}
